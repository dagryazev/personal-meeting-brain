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

EMBEDDING_MODEL = os.environ.get("MEETING_BRAIN_EMBED_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = 1024
# bge-m3 does not require a query/document prefix; we encode both directly.
# Auto-pick: "mps" on Apple Silicon, else "cpu". Override via env.
EMBEDDING_DEVICE = os.environ.get("MEETING_BRAIN_EMBED_DEVICE")

CHUNK_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 64
EMBED_BATCH_SIZE = 32
