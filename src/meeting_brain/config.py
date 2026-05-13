from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

TRANSCRIPTS_DIR: Path = Path(
    os.environ.get("MEETING_BRAIN_TRANSCRIPTS_DIR", PROJECT_ROOT / "transcripts")
)

DB_PATH: Path = Path(
    os.environ.get("MEETING_BRAIN_DB_PATH", PROJECT_ROOT / "data" / "meetings.db")
)

EMBEDDING_MODEL = os.environ.get("MEETING_BRAIN_EMBED_MODEL", "voyage-3")
EMBEDDING_DIM = 1024

CHUNK_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 64
EMBED_BATCH_SIZE = 32
