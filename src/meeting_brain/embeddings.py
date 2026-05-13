from __future__ import annotations

import os
from typing import Any

from meeting_brain.config import (
    EMBED_BATCH_SIZE,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
)

_client: Any | None = None


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


def _validate(vectors: list[list[float]]) -> list[list[float]]:
    for i, v in enumerate(vectors):
        if len(v) != EMBEDDING_DIM:
            raise RuntimeError(
                f"Voyage returned vector of length {len(v)} "
                f"(expected {EMBEDDING_DIM}) at index {i}"
            )
    return vectors


def _embed(texts: list[str], input_type: str) -> list[list[float]]:
    client = _get_client()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        result = client.embed(
            texts=batch,
            model=EMBEDDING_MODEL,
            input_type=input_type,
        )
        vectors.extend(result.embeddings)
    return vectors


def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return _validate(_embed(texts, input_type="document"))


def embed_query(text: str) -> list[float]:
    vectors = _embed([text], input_type="query")
    return _validate(vectors)[0]
