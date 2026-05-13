from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import sqlite_vec

from meeting_brain import embeddings
from meeting_brain.chunker import Chunk, chunk_text
from meeting_brain.config import (
    CHUNK_OVERLAP_TOKENS,
    CHUNK_TOKENS,
    EMBEDDING_DIM,
    TRANSCRIPTS_DIR,
)
from meeting_brain.db import connect

_DATE_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DATE_MDY_RE = re.compile(r"(?<!\d)(\d{2})[-/](\d{2})[-/](\d{4})(?!\d)")
_SLUG_RE = re.compile(r"^[a-z0-9]+([._\-][a-z0-9]+)+$", re.IGNORECASE)


def _extract_iso_date(stem: str) -> str | None:
    iso = _DATE_ISO_RE.search(stem)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}"
    mdy = _DATE_MDY_RE.search(stem)
    if mdy:
        return f"{mdy.group(3)}-{mdy.group(1)}-{mdy.group(2)}"
    return None


@dataclass
class IngestStats:
    added: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0


def parse_meeting_metadata(path: Path) -> tuple[str, str | None]:
    stem = path.stem
    iso_date = _extract_iso_date(stem)

    if _SLUG_RE.match(stem) or "_" in stem or "-" in stem:
        title = re.sub(r"[_\-]+", " ", stem).strip()
    else:
        title = stem
    return title, iso_date


def file_content_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _serialize_vector(vec: list[float]) -> bytes:
    return sqlite_vec.serialize_float32(vec)


def _purge_chunks(conn: sqlite3.Connection, meeting_id: int) -> None:
    # sqlite-vec virtual tables do NOT honor SQLite's foreign-key cascade,
    # so we must explicitly delete vec_chunks rows before removing the
    # parent chunks rows.
    conn.execute(
        "DELETE FROM vec_chunks WHERE chunk_id IN "
        "(SELECT id FROM chunks WHERE meeting_id = ?)",
        (meeting_id,),
    )
    conn.execute("DELETE FROM chunks WHERE meeting_id = ?", (meeting_id,))


def _insert_chunks(
    conn: sqlite3.Connection,
    meeting_id: int,
    chunks: list[Chunk],
    vectors: list[list[float]],
) -> None:
    for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
        cur = conn.execute(
            "INSERT INTO chunks (meeting_id, chunk_index, text, char_start, char_end, token_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                meeting_id,
                idx,
                chunk.text,
                chunk.char_start,
                chunk.char_end,
                chunk.token_count,
            ),
        )
        chunk_id = cur.lastrowid
        conn.execute(
            "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, _serialize_vector(vector)),
        )


def ingest_file(
    conn: sqlite3.Connection,
    path: Path,
    *,
    force: bool = False,
) -> Literal["added", "updated", "skipped", "failed"]:
    abs_path = str(path.resolve())
    try:
        raw_text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"failed: {abs_path} ({exc})", file=sys.stderr)
        return "failed"

    content_hash = file_content_hash(path)
    existing = conn.execute(
        "SELECT id, content_hash FROM meetings WHERE source_path = ?",
        (abs_path,),
    ).fetchone()

    if existing is not None and existing["content_hash"] == content_hash and not force:
        return "skipped"

    chunks = chunk_text(
        raw_text,
        chunk_tokens=CHUNK_TOKENS,
        overlap_tokens=CHUNK_OVERLAP_TOKENS,
    )
    if not chunks:
        print(f"failed: {abs_path} (no chunks produced)", file=sys.stderr)
        return "failed"

    try:
        vectors = embeddings.embed_documents([c.text for c in chunks])
    except Exception as exc:
        print(f"failed: {abs_path} (embedding error: {exc})", file=sys.stderr)
        return "failed"

    if len(vectors) != len(chunks):
        print(
            f"failed: {abs_path} (embedding count {len(vectors)} != chunk count {len(chunks)})",
            file=sys.stderr,
        )
        return "failed"
    for i, v in enumerate(vectors):
        if len(v) != EMBEDDING_DIM:
            print(
                f"failed: {abs_path} (embedding {i} has dim {len(v)}, expected {EMBEDDING_DIM})",
                file=sys.stderr,
            )
            return "failed"

    title, meeting_date = parse_meeting_metadata(path)
    word_count = len(raw_text.split())
    ingested_at = datetime.now(timezone.utc).isoformat()

    conn.execute("BEGIN")
    try:
        if existing is None:
            cur = conn.execute(
                "INSERT INTO meetings (source_path, title, meeting_date, participants, "
                "content_hash, word_count, ingested_at, raw_text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    abs_path,
                    title,
                    meeting_date,
                    None,
                    content_hash,
                    word_count,
                    ingested_at,
                    raw_text,
                ),
            )
            meeting_id = int(cur.lastrowid)
            status: Literal["added", "updated"] = "added"
        else:
            meeting_id = int(existing["id"])
            conn.execute(
                "UPDATE meetings SET title = ?, meeting_date = ?, content_hash = ?, "
                "word_count = ?, ingested_at = ?, raw_text = ? WHERE id = ?",
                (
                    title,
                    meeting_date,
                    content_hash,
                    word_count,
                    ingested_at,
                    raw_text,
                    meeting_id,
                ),
            )
            _purge_chunks(conn, meeting_id)
            status = "updated"

        _insert_chunks(conn, meeting_id, chunks, vectors)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"failed: {abs_path} (db error: {exc})", file=sys.stderr)
        return "failed"

    return status


def ingest_folder(
    conn: sqlite3.Connection,
    folder: Path | None = None,
    *,
    force: bool = False,
) -> IngestStats:
    target = Path(folder) if folder is not None else TRANSCRIPTS_DIR
    stats = IngestStats()
    if not target.exists():
        print(f"folder not found: {target}", file=sys.stderr)
        return stats

    files = sorted(p for p in target.rglob("*.md") if p.is_file())
    for path in files:
        status = ingest_file(conn, path, force=force)
        if status == "added":
            stats.added += 1
        elif status == "updated":
            stats.updated += 1
        elif status == "skipped":
            stats.skipped += 1
        else:
            stats.failed += 1
        print(f"{status}: {path}", file=sys.stderr)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest meeting transcripts into the local RAG store.")
    parser.add_argument(
        "--folder",
        type=Path,
        default=None,
        help="Folder of .md transcripts. Defaults to the configured transcripts dir.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed and replace chunks even when content_hash is unchanged.",
    )
    args = parser.parse_args()

    conn = connect()
    try:
        stats = ingest_folder(conn, args.folder, force=args.force)
    finally:
        conn.close()

    print(
        f"added={stats.added} updated={stats.updated} skipped={stats.skipped} failed={stats.failed}"
    )
