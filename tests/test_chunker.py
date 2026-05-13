from __future__ import annotations

import tiktoken

from meeting_brain.chunker import chunk_text


_ENC = tiktoken.get_encoding("cl100k_base")


def _make_text(num_tokens: int) -> str:
    # A pseudo-natural sentence stream that tokenizes to plenty of tokens.
    base = (
        "The quick brown fox jumps over the lazy dog near the river. "
        "Meanwhile, Alice and Bob discussed quarterly revenue projections "
        "while Carol prepared the slides for tomorrow's client review. "
    )
    out = ""
    while len(_ENC.encode(out)) < num_tokens:
        out += base
    return out


def test_short_text_returns_single_chunk():
    text = "Hello world, this is a tiny transcript."
    chunks = chunk_text(text, chunk_tokens=512, overlap_tokens=64)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.text == text
    assert chunk.char_start == 0
    assert chunk.char_end == len(text)
    assert chunk.token_count > 0


def test_chunks_cover_full_text():
    text = _make_text(2200)
    chunks = chunk_text(text, chunk_tokens=256, overlap_tokens=32)
    assert len(chunks) > 1

    # De-overlap by char positions: take chunk[0] entirely, then each next
    # chunk starting at max(previous char_end, current char_start).
    reconstructed = chunks[0].text
    cursor = chunks[0].char_end
    for chunk in chunks[1:]:
        start = max(cursor, chunk.char_start)
        if start < chunk.char_end:
            reconstructed += text[start:chunk.char_end]
        cursor = max(cursor, chunk.char_end)

    # Should reconstruct the original (or at minimum cover all non-trailing chars).
    assert reconstructed == text[: cursor]
    assert cursor == len(text) or cursor >= len(text) - 5


def test_overlap_is_respected():
    text = _make_text(1500)
    chunk_tokens = 256
    overlap_tokens = 64
    chunks = chunk_text(text, chunk_tokens=chunk_tokens, overlap_tokens=overlap_tokens)
    assert len(chunks) >= 2

    for prev, curr in zip(chunks, chunks[1:]):
        prev_tokens = _ENC.encode(prev.text)
        curr_tokens = _ENC.encode(curr.text)
        # The tail of prev should share ~overlap_tokens with the head of curr.
        max_check = min(len(prev_tokens), len(curr_tokens), overlap_tokens + 20)
        shared = 0
        for n in range(max_check, 0, -1):
            if prev_tokens[-n:] == curr_tokens[:n]:
                shared = n
                break
        assert abs(shared - overlap_tokens) <= 5, (
            f"expected overlap ~{overlap_tokens}, got {shared}"
        )


def test_empty_input_returns_empty_list():
    assert chunk_text("", chunk_tokens=512, overlap_tokens=64) == []
