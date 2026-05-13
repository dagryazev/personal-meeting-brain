from __future__ import annotations

import sqlite3
from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import FastMCP

from meeting_brain import ingest, search
from meeting_brain.db import connect

mcp = FastMCP("meeting-brain")


def _open_conn() -> sqlite3.Connection:
    # Each tool invocation gets its own short-lived connection. sqlite-vec can
    # misbehave when a single connection is shared across threads, and tool
    # calls are infrequent enough that the connect cost is negligible.
    return connect()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


@mcp.tool()
def search_meetings(
    query: str,
    top_k: int = 8,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    """Search meeting transcripts for a natural-language query. Returns up to `top_k`
    chunks ranked by semantic similarity, with the meeting source path, date, and
    a snippet for citation.

    Use this when the user asks about anything that might have been discussed in a
    meeting: decisions, action items, who said what, project status, etc. Results
    are ordered by relevance (lower score = better match). Always cite the
    `source_path` and `meeting_date` of the chunks you use.

    Args:
        query: The natural-language question or topic to search for.
        top_k: Maximum number of chunks to return (default 8).
        date_from: Optional ISO date (YYYY-MM-DD) lower bound, inclusive.
        date_to: Optional ISO date (YYYY-MM-DD) upper bound, inclusive.
    """
    conn = _open_conn()
    try:
        hits = search.search(
            conn,
            query,
            top_k=top_k,
            date_from=date_from,
            date_to=date_to,
        )
        return [asdict(h) for h in hits]
    finally:
        conn.close()


@mcp.tool()
def get_meeting(
    source_path: str | None = None,
    meeting_id: int | None = None,
) -> dict[str, Any]:
    """Retrieve a full meeting transcript by its source path or numeric id. Use this
    after `search_meetings` to read more context around a hit.

    Exactly one of `source_path` or `meeting_id` must be provided. The returned
    dict includes the full `raw_text` of the transcript plus all metadata
    (title, meeting_date, participants, word_count, ingested_at).

    Args:
        source_path: Absolute or relative path to the .md transcript.
        meeting_id: Numeric meeting id (alternative to source_path).
    """
    if (source_path is None) == (meeting_id is None):
        raise ValueError(
            "Provide exactly one of `source_path` or `meeting_id`."
        )

    conn = _open_conn()
    try:
        if meeting_id is not None:
            row = conn.execute(
                "SELECT * FROM meetings WHERE id = ?",
                (int(meeting_id),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM meetings WHERE source_path = ?",
                (source_path,),
            ).fetchone()

        result = _row_to_dict(row)
        if result is None:
            raise ValueError(
                f"Meeting not found (source_path={source_path!r}, meeting_id={meeting_id!r})."
            )
        return result
    finally:
        conn.close()


@mcp.tool()
def list_meetings(
    limit: int = 50,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    """List indexed meetings with metadata only (no transcript bodies). Useful for
    browsing what is available before searching.

    Results are ordered by `meeting_date` descending (NULLs last), then by id
    descending. Each item contains: id, source_path, title, meeting_date,
    word_count, ingested_at.

    Args:
        limit: Maximum number of meetings to return (default 50, max 500).
        date_from: Optional ISO date lower bound, inclusive.
        date_to: Optional ISO date upper bound, inclusive.
    """
    capped = max(1, min(int(limit), 500))

    where_parts: list[str] = []
    params: list[Any] = []
    if date_from is not None:
        where_parts.append("(meeting_date IS NULL OR meeting_date >= ?)")
        params.append(date_from)
    if date_to is not None:
        where_parts.append("(meeting_date IS NULL OR meeting_date <= ?)")
        params.append(date_to)
    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    sql = (
        "SELECT id, source_path, title, meeting_date, word_count, ingested_at "
        f"FROM meetings {where_sql} "
        "ORDER BY (meeting_date IS NULL), meeting_date DESC, id DESC "
        "LIMIT ?"
    )
    params.append(capped)

    conn = _open_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [
            {
                "id": int(r["id"]),
                "source_path": r["source_path"],
                "title": r["title"],
                "meeting_date": r["meeting_date"],
                "word_count": r["word_count"],
                "ingested_at": r["ingested_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


@mcp.tool()
def reindex(force: bool = False) -> dict[str, int]:
    """(Re)scan the transcripts folder and ingest any new or changed .md files.
    Returns counts of files added, updated, skipped (unchanged), and failed.

    Use this when the user adds new transcripts, edits existing ones, or asks
    to refresh the index. Set `force=true` to re-embed every file regardless
    of its content hash (slower, costs Voyage API tokens).

    Args:
        force: If true, re-embed every file regardless of content hash (default false).
    """
    conn = _open_conn()
    try:
        stats = ingest.ingest_folder(conn, force=force)
        return {
            "added": stats.added,
            "updated": stats.updated,
            "skipped": stats.skipped,
            "failed": stats.failed,
        }
    finally:
        conn.close()


@mcp.resource("meetings://index")
def meetings_index() -> str:
    """Markdown table of all indexed meetings (id, date, title, path)."""
    conn = _open_conn()
    try:
        rows = conn.execute(
            "SELECT id, source_path, title, meeting_date "
            "FROM meetings "
            "ORDER BY (meeting_date IS NULL), meeting_date DESC, id DESC"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return "# Meetings index\n\n_No meetings indexed yet._\n"

    lines = [
        "# Meetings index",
        "",
        "| id | date | title | path |",
        "|---:|------|-------|------|",
    ]
    for r in rows:
        date = r["meeting_date"] or ""
        title = (r["title"] or "").replace("|", "\\|")
        path = (r["source_path"] or "").replace("|", "\\|")
        lines.append(f"| {int(r['id'])} | {date} | {title} | {path} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
