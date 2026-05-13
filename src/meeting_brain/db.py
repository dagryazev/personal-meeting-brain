from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec

from meeting_brain.config import DB_PATH

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meetings (
  id           INTEGER PRIMARY KEY,
  source_path  TEXT UNIQUE NOT NULL,
  title        TEXT,
  meeting_date TEXT,
  participants TEXT,
  content_hash TEXT NOT NULL,
  word_count   INTEGER,
  ingested_at  TEXT NOT NULL,
  raw_text     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
  id           INTEGER PRIMARY KEY,
  meeting_id   INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
  chunk_index  INTEGER NOT NULL,
  text         TEXT NOT NULL,
  char_start   INTEGER,
  char_end     INTEGER,
  token_count  INTEGER,
  UNIQUE(meeting_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_meeting ON chunks(meeting_id);
"""

_VEC_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
  chunk_id  INTEGER PRIMARY KEY,
  embedding FLOAT[1024]
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    init_schema(conn)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)
    # vec0 virtual table is created via a separate statement so that older
    # SQLite builds without sqlite-vec loaded still produce a usable error.
    conn.execute(_VEC_SCHEMA_SQL.strip())
    conn.commit()
