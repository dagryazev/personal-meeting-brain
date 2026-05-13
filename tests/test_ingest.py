from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from meeting_brain import embeddings, ingest
from meeting_brain.config import EMBEDDING_DIM
from meeting_brain.db import connect
from meeting_brain.ingest import (
    ingest_file,
    ingest_folder,
    parse_meeting_metadata,
)


def _fake_vector_for(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # Repeat the 32-byte digest as deterministic float seeds.
    vec: list[float] = []
    while len(vec) < EMBEDDING_DIM:
        for b in digest:
            vec.append((b / 255.0) - 0.5)
            if len(vec) == EMBEDDING_DIM:
                break
    return vec


def _fake_embed_documents(texts: list[str]) -> list[list[float]]:
    return [_fake_vector_for(t) for t in texts]


@pytest.fixture
def patched_embeddings(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_documents", _fake_embed_documents)
    # ingest imports the `embeddings` module and calls embeddings.embed_documents,
    # so patching the module attribute is sufficient.
    yield


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    c = connect(db_path)
    yield c
    c.close()


@pytest.fixture
def sample_text() -> str:
    base = (
        "Project sync meeting. Alice walked through the API design. "
        "Bob raised concerns about retry semantics on the worker queue. "
        "Carol proposed a feature flag rollout for the new search ranker. "
    )
    return base * 80  # enough tokens to span multiple chunks


def test_parse_meeting_metadata(tmp_path):
    p1 = tmp_path / "2024-01-15_team_sync.md"
    p1.write_text("x")
    title, date = parse_meeting_metadata(p1)
    assert date == "2024-01-15"
    assert title == "2024 01 15 team sync"

    p2 = tmp_path / "Standup Notes.md"
    p2.write_text("x")
    title, date = parse_meeting_metadata(p2)
    assert date is None
    assert title == "Standup Notes"

    p3 = tmp_path / "weekly-review-q4.md"
    p3.write_text("x")
    title, date = parse_meeting_metadata(p3)
    assert date is None
    assert title == "weekly review q4"

    p4 = tmp_path / "Daily Meet (cleanup) - 05-06-2026-20260513115303.md"
    p4.write_text("x")
    _, date = parse_meeting_metadata(p4)
    assert date == "2026-05-06"

    p5 = Path("call_04-29-2026.md")
    _, date = parse_meeting_metadata(p5)
    assert date == "2026-04-29"


def test_ingest_creates_meeting_and_chunks(conn, tmp_path, sample_text, patched_embeddings):
    f = tmp_path / "2024-02-01_demo.md"
    f.write_text(sample_text, encoding="utf-8")

    status = ingest_file(conn, f)
    assert status == "added"

    meetings = conn.execute("SELECT * FROM meetings").fetchall()
    assert len(meetings) == 1
    assert meetings[0]["meeting_date"] == "2024-02-01"
    assert meetings[0]["raw_text"] == sample_text
    assert meetings[0]["word_count"] == len(sample_text.split())

    chunks = conn.execute(
        "SELECT * FROM chunks WHERE meeting_id = ? ORDER BY chunk_index",
        (meetings[0]["id"],),
    ).fetchall()
    assert len(chunks) > 1
    for i, row in enumerate(chunks):
        assert row["chunk_index"] == i
        assert row["text"]
        assert row["token_count"] > 0

    vec_count = conn.execute("SELECT COUNT(*) AS n FROM vec_chunks").fetchone()["n"]
    assert vec_count == len(chunks)


def test_ingest_is_idempotent(conn, tmp_path, sample_text, patched_embeddings):
    f = tmp_path / "session.md"
    f.write_text(sample_text, encoding="utf-8")

    assert ingest_file(conn, f) == "added"
    meetings_before = conn.execute("SELECT COUNT(*) AS n FROM meetings").fetchone()["n"]
    chunks_before = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
    vec_before = conn.execute("SELECT COUNT(*) AS n FROM vec_chunks").fetchone()["n"]

    assert ingest_file(conn, f) == "skipped"

    assert conn.execute("SELECT COUNT(*) AS n FROM meetings").fetchone()["n"] == meetings_before
    assert conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"] == chunks_before
    assert conn.execute("SELECT COUNT(*) AS n FROM vec_chunks").fetchone()["n"] == vec_before


def test_ingest_updates_on_content_change(conn, tmp_path, sample_text, patched_embeddings):
    f = tmp_path / "session.md"
    f.write_text(sample_text, encoding="utf-8")
    assert ingest_file(conn, f) == "added"

    first_chunks = [
        (r["chunk_index"], r["text"])
        for r in conn.execute(
            "SELECT chunk_index, text FROM chunks ORDER BY chunk_index"
        ).fetchall()
    ]
    assert first_chunks

    new_text = sample_text + "\n\nADDENDUM: post-meeting notes appended later."
    f.write_text(new_text, encoding="utf-8")
    assert ingest_file(conn, f) == "updated"

    second_chunk_ids = [
        r["id"] for r in conn.execute("SELECT id FROM chunks ORDER BY id").fetchall()
    ]
    second_chunks = [
        (r["chunk_index"], r["text"])
        for r in conn.execute(
            "SELECT chunk_index, text FROM chunks ORDER BY chunk_index"
        ).fetchall()
    ]
    # Old chunks must be gone — i.e. the content of the chunk set changed
    # (either more chunks or the last chunk extended with the addendum).
    assert second_chunks != first_chunks
    assert second_chunks

    # vec_chunks should reference exactly the current chunks (1:1).
    vec_ids = [
        r["chunk_id"] for r in conn.execute("SELECT chunk_id FROM vec_chunks").fetchall()
    ]
    assert sorted(vec_ids) == sorted(second_chunk_ids)

    # Only one meeting row, hash updated.
    meetings = conn.execute("SELECT * FROM meetings").fetchall()
    assert len(meetings) == 1
    assert meetings[0]["raw_text"] == new_text


def test_ingest_folder_collects_stats(conn, tmp_path, sample_text, patched_embeddings):
    (tmp_path / "a.md").write_text(sample_text, encoding="utf-8")
    (tmp_path / "b.md").write_text(sample_text + " extra", encoding="utf-8")

    stats = ingest_folder(conn, tmp_path)
    assert stats.added == 2
    assert stats.updated == 0
    assert stats.failed == 0

    stats2 = ingest_folder(conn, tmp_path)
    assert stats2.skipped == 2
    assert stats2.added == 0
