from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

import sqlite_vec

from meeting_brain import embeddings

_SNIPPET_MAX = 600
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class SearchHit:
    meeting_id: int
    source_path: str
    title: str | None
    meeting_date: str | None
    chunk_index: int
    snippet: str
    score: float


def _snippet(text: str) -> str:
    collapsed = _WHITESPACE_RE.sub(" ", text).strip()
    if len(collapsed) <= _SNIPPET_MAX:
        return collapsed
    return collapsed[:_SNIPPET_MAX] + "..."


def _passes_date_filter(
    meeting_date: str | None,
    date_from: str | None,
    date_to: str | None,
) -> bool:
    # sqlite-vec's MATCH operator does not compose cleanly with arbitrary
    # WHERE clauses on joined tables, so we over-fetch then filter in Python.
    # Undated meetings always pass: losing them silently is worse than
    # including them when a user supplies a date range.
    if meeting_date is None:
        return True
    if date_from is not None and meeting_date < date_from:
        return False
    if date_to is not None and meeting_date > date_to:
        return False
    return True


def search(
    conn: sqlite3.Connection,
    query: str,
    *,
    top_k: int = 8,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[SearchHit]:
    if not query or not query.strip():
        return []
    if top_k <= 0:
        return []

    qvec = embeddings.embed_query(query)
    qblob = sqlite_vec.serialize_float32(qvec)

    overfetch = max(top_k * 3, top_k)
    rows = conn.execute(
        """
        SELECT chunk_id, distance
        FROM vec_chunks
        WHERE embedding MATCH ?
        ORDER BY distance
        LIMIT ?
        """,
        (qblob, overfetch),
    ).fetchall()

    if not rows:
        return []

    chunk_ids = [int(r["chunk_id"]) for r in rows]
    distances = {int(r["chunk_id"]): float(r["distance"]) for r in rows}

    placeholders = ",".join("?" for _ in chunk_ids)
    join_rows = conn.execute(
        f"""
        SELECT
            c.id           AS chunk_id,
            c.chunk_index  AS chunk_index,
            c.text         AS text,
            m.id           AS meeting_id,
            m.source_path  AS source_path,
            m.title        AS title,
            m.meeting_date AS meeting_date
        FROM chunks c
        JOIN meetings m ON m.id = c.meeting_id
        WHERE c.id IN ({placeholders})
        """,
        chunk_ids,
    ).fetchall()

    by_chunk = {int(r["chunk_id"]): r for r in join_rows}

    hits: list[SearchHit] = []
    for cid in chunk_ids:
        row = by_chunk.get(cid)
        if row is None:
            continue
        if not _passes_date_filter(row["meeting_date"], date_from, date_to):
            continue
        hits.append(
            SearchHit(
                meeting_id=int(row["meeting_id"]),
                source_path=str(row["source_path"]),
                title=row["title"],
                meeting_date=row["meeting_date"],
                chunk_index=int(row["chunk_index"]),
                snippet=_snippet(row["text"]),
                score=distances[cid],
            )
        )
        if len(hits) >= top_k:
            break

    return hits
