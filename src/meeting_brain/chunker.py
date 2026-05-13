from __future__ import annotations

from dataclasses import dataclass

import tiktoken

_ENCODING_NAME = "cl100k_base"
_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding(_ENCODING_NAME)
    return _encoder


@dataclass
class Chunk:
    text: str
    char_start: int
    char_end: int
    token_count: int


def chunk_text(
    text: str,
    chunk_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[Chunk]:
    if not text:
        return []
    if chunk_tokens <= 0:
        raise ValueError("chunk_tokens must be positive")
    if overlap_tokens < 0 or overlap_tokens >= chunk_tokens:
        raise ValueError("overlap_tokens must be in [0, chunk_tokens)")

    encoder = _get_encoder()
    token_ids = encoder.encode(text)

    if not token_ids:
        return []

    # Short text: single chunk covering the whole input (skip pure whitespace).
    if len(token_ids) <= chunk_tokens:
        if text.strip() == "":
            return []
        return [
            Chunk(
                text=text,
                char_start=0,
                char_end=len(text),
                token_count=len(token_ids),
            )
        ]

    n = len(token_ids)

    # Character offset at token boundary k = len(decode(tokens[:k])). tiktoken's
    # decode is round-trip safe on the full token list, so this gives the exact
    # char offset of token k inside the original text without fragile substring
    # searches that can land on mid-word boundaries (a real gotcha with cl100k:
    # decoded sub-sequences can drop leading spaces, so text.find() may match a
    # spurious in-word occurrence).
    def offset_at(k: int) -> int:
        if k <= 0:
            return 0
        if k >= n:
            return len(text)
        return len(encoder.decode(token_ids[:k]))

    step = chunk_tokens - overlap_tokens
    chunks: list[Chunk] = []
    start = 0
    while start < n:
        end = min(start + chunk_tokens, n)
        char_start = offset_at(start)
        char_end = offset_at(end)
        chunk_str = text[char_start:char_end]

        if chunk_str.strip() == "":
            if end == n:
                break
            start += step
            continue

        chunks.append(
            Chunk(
                text=chunk_str,
                char_start=char_start,
                char_end=char_end,
                token_count=end - start,
            )
        )

        if end == n:
            break
        start += step

    return chunks
