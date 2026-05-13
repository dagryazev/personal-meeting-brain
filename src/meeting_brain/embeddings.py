from __future__ import annotations

from typing import Any

from meeting_brain.config import (
    EMBED_BATCH_SIZE,
    EMBEDDING_DEVICE,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
)

_model: Any | None = None


def _default_device() -> str:
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _get_model() -> Any:
    global _model
    if _model is not None:
        return _model
    from sentence_transformers import SentenceTransformer

    device = EMBEDDING_DEVICE or _default_device()
    _model = SentenceTransformer(EMBEDDING_MODEL, device=device)
    return _model


def _validate(vectors: list[list[float]]) -> list[list[float]]:
    for i, v in enumerate(vectors):
        if len(v) != EMBEDDING_DIM:
            raise RuntimeError(
                f"Embedding model returned vector of length {len(v)} "
                f"(expected {EMBEDDING_DIM}) at index {i}"
            )
    return vectors


def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(
        texts,
        batch_size=EMBED_BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return _validate([v.tolist() for v in vectors])


def embed_query(text: str) -> list[float]:
    model = _get_model()
    vec = model.encode(
        text,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return _validate([vec.tolist()])[0]
