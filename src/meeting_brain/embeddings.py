from __future__ import annotations

import os
import sys
import time
from typing import Any

from meeting_brain.config import (
    EMBED_BATCH_SIZE,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
)

_client: Any | None = None

# Voyage free tier is 3 RPM / 10K TPM. With retries + 25s waits we degrade
# gracefully instead of failing the whole ingest run.
_MAX_RETRIES = 6
_BASE_BACKOFF_S = 5.0


def _get_client() -> Any:
    global _client
    if _client is not None:
        return _client

    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "VOYAGE_API_KEY is not set. Add it to .env or your environment "
            "before running ingest or search."
        )

    import voyageai

    _client = voyageai.Client(api_key=api_key)
    return _client


def _is_rate_limit(exc: BaseException) -> bool:
    # voyageai raises a typed RateLimitError; we also pattern-match on the
    # message because older SDK versions wrap it in a generic Exception.
    name = type(exc).__name__
    if name in {"RateLimitError", "APIStatusError"}:
        return True
    msg = str(exc).lower()
    return "rate limit" in msg or "429" in msg or "rpm" in msg or "tpm" in msg


def _validate(vectors: list[list[float]]) -> list[list[float]]:
    for i, v in enumerate(vectors):
        if len(v) != EMBEDDING_DIM:
            raise RuntimeError(
                f"Voyage returned vector of length {len(v)} "
                f"(expected {EMBEDDING_DIM}) at index {i}"
            )
    return vectors


def _embed_batch(batch: list[str], input_type: str) -> list[list[float]]:
    client = _get_client()
    last_exc: BaseException | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            result = client.embed(
                texts=batch,
                model=EMBEDDING_MODEL,
                input_type=input_type,
            )
            return list(result.embeddings)
        except Exception as exc:
            last_exc = exc
            if not _is_rate_limit(exc) or attempt == _MAX_RETRIES - 1:
                raise
            wait = _BASE_BACKOFF_S * (2**attempt)
            print(
                f"voyage rate-limited, retrying in {wait:.0f}s "
                f"(attempt {attempt + 1}/{_MAX_RETRIES})",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(wait)
    # Unreachable, but keeps type checkers happy.
    raise last_exc if last_exc else RuntimeError("voyage embed: unknown failure")


def _embed(texts: list[str], input_type: str) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        vectors.extend(_embed_batch(batch, input_type))
    return vectors


def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return _validate(_embed(texts, input_type="document"))


def embed_query(text: str) -> list[float]:
    vectors = _embed([text], input_type="query")
    return _validate(vectors)[0]
