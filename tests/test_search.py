from __future__ import annotations

import hashlib

import pytest

from meeting_brain import embeddings, ingest, search
from meeting_brain.config import EMBEDDING_DIM
from meeting_brain.db import connect
from meeting_brain.ingest import ingest_file
from meeting_brain.search import SearchHit


_TOKEN_MARKERS = ("Alice", "Bob", "Carol", "Dave", "search ranker", "retry")


def _fake_vector_for(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec: list[float] = []
    while len(vec) < EMBEDDING_DIM:
        for b in digest:
            vec.append((b / 255.0) - 0.5)
            if len(vec) == EMBEDDING_DIM:
                break

    # Topic-aware bias: push known markers into dedicated dimensions so a
    # query containing the same marker produces a vector close (in cosine
    # distance) to chunks containing it. Without this nudge, the SHA hash
    # is too uncorrelated for semantic-search tests to be meaningful.
    for i, marker in enumerate(_TOKEN_MARKERS):
        if marker.lower() in text.lower():
            vec[i] = 5.0
    return vec


def _fake_embed_documents(texts: list[str]) -> list[list[float]]:
    return [_fake_vector_for(t) for t in texts]


def _fake_embed_query(text: str) -> list[float]:
    return _fake_vector_for(text)


@pytest.fixture
def patched_embeddings(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_documents", _fake_embed_documents)
    monkeypatch.setattr(embeddings, "embed_query", _fake_embed_query)
    # search.py imports the `embeddings` module and calls embeddings.embed_query
    # via attribute lookup, so patching the module attribute is sufficient.
    yield


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    c = connect(db_path)
    yield c
    c.close()


def test_search_returns_hits_ordered_by_score(conn, tmp_path, patched_embeddings):
    alice = tmp_path / "2024-03-01_alice_sync.md"
    alice.write_text(
        "Alice presented the new pipeline. " * 50, encoding="utf-8"
    )
    bob = tmp_path / "2024-03-02_bob_review.md"
    bob.write_text(
        "Bob led the architecture review. " * 50, encoding="utf-8"
    )

    assert ingest_file(conn, alice) == "added"
    assert ingest_file(conn, bob) == "added"

    hits = search.search(conn, "Alice", top_k=5)
    assert hits, "expected at least one hit"
    assert all(isinstance(h, SearchHit) for h in hits)
    assert "alice" in hits[0].snippet.lower()
    scores = [h.score for h in hits]
    assert scores == sorted(scores), "results must be ordered by ascending distance"


def test_search_respects_date_filter(conn, tmp_path, patched_embeddings):
    early = tmp_path / "2023-01-15_alice_kickoff.md"
    early.write_text("Alice opened the kickoff. " * 50, encoding="utf-8")
    late = tmp_path / "2024-08-15_alice_recap.md"
    late.write_text("Alice closed the recap. " * 50, encoding="utf-8")

    assert ingest_file(conn, early) == "added"
    assert ingest_file(conn, late) == "added"

    hits = search.search(
        conn, "Alice", top_k=10, date_from="2024-01-01", date_to="2024-12-31"
    )
    assert hits, "expected at least one hit in 2024"
    for h in hits:
        assert h.meeting_date is None or h.meeting_date >= "2024-01-01"
        assert h.meeting_date is None or h.meeting_date <= "2024-12-31"
    assert any("recap" in (h.source_path or "").lower() for h in hits)
    assert not any("kickoff" in (h.source_path or "").lower() for h in hits)


def test_search_includes_undated_meetings_in_filter(conn, tmp_path, patched_embeddings):
    undated = tmp_path / "Alice Brainstorm.md"
    undated.write_text("Alice brainstormed ideas. " * 50, encoding="utf-8")
    dated = tmp_path / "2019-01-01_alice_old.md"
    dated.write_text("Alice covered old material. " * 50, encoding="utf-8")

    assert ingest_file(conn, undated) == "added"
    assert ingest_file(conn, dated) == "added"

    hits = search.search(
        conn, "Alice", top_k=10, date_from="2024-01-01", date_to="2024-12-31"
    )
    assert hits, "undated meeting must pass through date filter"
    paths = [h.source_path for h in hits]
    assert any("Brainstorm" in p for p in paths)
    assert not any("alice_old" in p for p in paths)


def test_search_truncates_long_snippets(conn, tmp_path, patched_embeddings):
    f = tmp_path / "2024-04-01_alice_long.md"
    f.write_text("Alice " + ("blah " * 5000), encoding="utf-8")
    assert ingest_file(conn, f) == "added"

    hits = search.search(conn, "Alice", top_k=3)
    assert hits
    for h in hits:
        assert len(h.snippet) <= 603


def test_search_empty_query_returns_empty(conn, patched_embeddings):
    assert search.search(conn, "") == []
    assert search.search(conn, "   ") == []
