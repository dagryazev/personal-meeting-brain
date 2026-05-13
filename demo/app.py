"""Streamlit demo for personal-meeting-brain.

Run locally:
    uv run streamlit run demo/app.py

Required environment variables:
    VOYAGE_API_KEY  — for embedding queries
    GEMINI_API_KEY  — for LLM generation
"""
from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import asdict
from datetime import date
from typing import Iterable

import streamlit as st

from meeting_brain import search
from meeting_brain.db import connect

import rate_limit

SAMPLE_QUESTIONS = [
    "What was discussed in the database outage postmortem?",
    "What are Acme's top priorities as a customer?",
    "What was decided about hiring the backend engineer?",
    "Why did the team pick TimescaleDB over ClickHouse?",
    "What is the quarterly plan for marketplace integrations?",
]

SYSTEM_PROMPT = """You are an assistant for browsing meeting transcripts. Answer the user's
question using ONLY the content of the supplied transcript fragments.

Rules:
1. Cite every fact in the form [N], where N is the fragment number.
2. If the fragments do not contain an answer, say plainly: "Not found in the transcripts".
3. Do not invent details that are not in the fragments.
4. Answer in the same language the user asked in.
5. Be concise but informative. Bullet lists are welcome."""


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    from google import genai

    return genai.Client(api_key=api_key)


def _open_conn() -> sqlite3.Connection:
    """Open a fresh sqlite-vec connection per request.

    sqlite-vec misbehaves when a single connection is shared across threads,
    and Streamlit reruns the script on each interaction — keeping connections
    per-run is the safe pattern.
    """
    return connect()


def _client_ip() -> str:
    """Best-effort client IP for rate limiting.

    Behind Railway / typical reverse proxies, the original IP arrives in
    X-Forwarded-For. Fall back to X-Real-IP, then a stable session marker
    so two anonymous local users still get separate buckets.
    """
    try:
        headers = dict(st.context.headers or {})
    except Exception:
        headers = {}
    xff = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    real = headers.get("X-Real-IP") or headers.get("x-real-ip")
    if real:
        return real.strip()
    return "local"


def _index_stats() -> tuple[int, int]:
    conn = _open_conn()
    try:
        meetings = conn.execute("SELECT COUNT(*) AS n FROM meetings").fetchone()["n"]
        chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        return int(meetings), int(chunks)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _build_context(hits: list[search.SearchHit]) -> str:
    parts: list[str] = []
    for i, h in enumerate(hits, start=1):
        header = f"[{i}] ({h.meeting_date or 'undated'} — {h.title or 'untitled'})"
        parts.append(f"{header}\n{h.snippet}")
    return "\n\n".join(parts)


def _stream_answer(query: str, hits: list[search.SearchHit]) -> Iterable[str]:
    client = _gemini_client()
    if client is None:
        yield "**GEMINI_API_KEY is not set.** Add the key to your environment and restart the app."
        return

    if not hits:
        yield "No relevant fragments found in the index. Try rephrasing the question or widening the date range."
        return

    context = _build_context(hits)
    user_message = (
        f"Transcript fragments:\n\n{context}\n\n"
        f"User question: {query}"
    )

    try:
        stream = client.models.generate_content_stream(
            model="gemini-2.5-flash",
            contents=user_message,
            config={"system_instruction": SYSTEM_PROMPT, "temperature": 0.2},
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text
    except Exception as exc:
        yield f"\n\n_Gemini call failed: {exc}_"


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Personal Meeting Brain — Demo",
    page_icon=":brain:",
    layout="wide",
)

st.title("Personal Meeting Brain")
st.caption(
    "Local RAG over meeting transcripts. SQLite + sqlite-vec for storage, "
    "Voyage AI `voyage-3` for embeddings, Gemini 2.5 Flash for generation."
)

# Top stats bar
meetings_count, chunks_count = _index_stats()
c1, c2, c3 = st.columns(3)
c1.metric("Meetings indexed", meetings_count)
c2.metric("Chunks (≈512 tokens)", chunks_count)
c3.metric("Embedding model", "voyage-3 (1024d)")

if meetings_count == 0:
    st.warning(
        "Index is empty. Drop `.md` transcripts into `transcripts/` and run "
        "`uv run meeting-brain-ingest` (requires `VOYAGE_API_KEY`)."
    )

# Sidebar controls
with st.sidebar:
    st.header("Search parameters")
    top_k = st.slider("Top-K chunks for context", min_value=3, max_value=15, value=6)
    use_date_filter = st.checkbox("Filter by date")
    date_from_str: str | None = None
    date_to_str: str | None = None
    if use_date_filter:
        today = date.today()
        df = st.date_input("From", value=date(today.year - 1, today.month, today.day))
        dt = st.date_input("To", value=today)
        date_from_str = df.isoformat()
        date_to_str = dt.isoformat()

    st.divider()
    st.subheader("Example questions")
    for q in SAMPLE_QUESTIONS:
        if st.button(q, use_container_width=True, key=f"sample-{hash(q)}"):
            st.session_state["query"] = q

# Query input
query = st.text_input(
    "Ask about the meetings:",
    value=st.session_state.get("query", ""),
    placeholder="e.g. What did we decide about archiving events?",
    key="query",
)

ask = st.button("Search & answer", type="primary", disabled=not query.strip())

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if ask and query.strip():
    ip = _client_ip()
    decision = rate_limit.check(ip)
    if not decision.allowed:
        st.divider()
        st.error(
            f"{decision.reason} Try again in {decision.retry_after_s}s."
        )
        st.stop()

    t_search = time.perf_counter()
    conn = _open_conn()
    try:
        hits = search.search(
            conn,
            query,
            top_k=top_k,
            date_from=date_from_str,
            date_to=date_to_str,
        )
    finally:
        conn.close()
    search_ms = (time.perf_counter() - t_search) * 1000

    st.divider()
    st.subheader("Answer")
    st.caption(
        f"Fragments retrieved: {len(hits)} · search took {search_ms:.0f} ms · "
        f"{decision.remaining_minute}/min, "
        f"{decision.remaining_hour}/hour, {decision.remaining_day}/day left from this IP"
    )

    answer_placeholder = st.empty()

    t_gen = time.perf_counter()
    full_answer = ""
    for piece in _stream_answer(query, hits):
        full_answer += piece
        answer_placeholder.markdown(full_answer)
    gen_ms = (time.perf_counter() - t_gen) * 1000

    st.caption(f"Generation took {gen_ms:.0f} ms")

    if hits:
        st.subheader("Sources")
        for i, h in enumerate(hits, start=1):
            with st.expander(
                f"[{i}] {h.meeting_date or 'undated'} — {h.title or h.source_path} "
                f"· score={h.score:.3f}"
            ):
                meta_cols = st.columns(3)
                meta_cols[0].markdown(f"**Date:** {h.meeting_date or '—'}")
                meta_cols[1].markdown(f"**Chunk #:** {h.chunk_index}")
                meta_cols[2].markdown(f"**Score (cosine dist):** {h.score:.4f}")
                st.markdown("**Fragment:**")
                st.markdown(f"> {h.snippet}")
                st.caption(f"Source: `{h.source_path}`")

with st.sidebar:
    st.divider()
    rem_min, rem_hour, rem_day = rate_limit.snapshot(_client_ip())
    st.caption(
        f"Budget from this IP: **{rem_min}** this minute · "
        f"**{rem_hour}** this hour · **{rem_day}** today."
    )
    with st.expander("How it works"):
        st.markdown(
            """
1. The question is embedded via `voyage-3` (`input_type=query`).
2. SQLite + `sqlite-vec` finds the K nearest chunks by cosine distance.
3. Retrieved chunks plus the question are sent to Gemini 2.5 Flash with an instruction to cite sources.
4. The answer streams into the UI; sources expand below.

Document embeddings are computed once at ingest time (`input_type=document`).
This asymmetric encoding noticeably improves relevance over using one encoder for both.
            """
        )
