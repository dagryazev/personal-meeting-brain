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

SAMPLE_QUESTIONS = [
    "Что обсуждали на постмортеме по падению базы?",
    "Какие приоритеты у клиента Acme?",
    "Что решили по найму бэкенд-инженера?",
    "Почему выбрали TimescaleDB, а не ClickHouse?",
    "Какой план на квартал по интеграциям с маркетплейсами?",
]

SYSTEM_PROMPT = """Ты — ассистент по корпоративным митингам. Отвечай на вопрос пользователя,
используя ТОЛЬКО содержимое предоставленных фрагментов транскриптов.

Правила:
1. Для каждого факта указывай источник в формате [N], где N — номер фрагмента.
2. Если в фрагментах нет ответа — честно скажи: "Не нашёл этого в транскриптах".
3. Не выдумывай детали, не упомянутые во фрагментах.
4. Отвечай на том же языке, что и вопрос.
5. Будь кратким, но информативным. Маркированные списки приветствуются."""


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
        header = f"[{i}] ({h.meeting_date or 'без даты'} — {h.title or 'без названия'})"
        parts.append(f"{header}\n{h.snippet}")
    return "\n\n".join(parts)


def _stream_answer(query: str, hits: list[search.SearchHit]) -> Iterable[str]:
    client = _gemini_client()
    if client is None:
        yield "**GEMINI_API_KEY не задан.** Добавь ключ в переменные окружения и перезапусти приложение."
        return

    if not hits:
        yield "Не нашёл подходящих фрагментов в индексе. Попробуй переформулировать вопрос или расширить диапазон дат."
        return

    context = _build_context(hits)
    user_message = (
        f"Фрагменты транскриптов:\n\n{context}\n\n"
        f"Вопрос пользователя: {query}"
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
        yield f"\n\n_Ошибка при обращении к Gemini: {exc}_"


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
    "Локальный RAG над транскриптами митингов. SQLite + sqlite-vec для хранения, "
    "Voyage AI `voyage-3` для embeddings, Gemini 2.5 Flash для генерации."
)

# Top stats bar
meetings_count, chunks_count = _index_stats()
c1, c2, c3 = st.columns(3)
c1.metric("Митингов в индексе", meetings_count)
c2.metric("Чанков (≈512 токенов)", chunks_count)
c3.metric("Embedding model", "voyage-3 (1024d)")

if meetings_count == 0:
    st.warning(
        "Индекс пуст. Положи `.md` транскрипты в `transcripts/` и запусти "
        "`uv run meeting-brain-ingest` (требуется `VOYAGE_API_KEY`)."
    )

# Sidebar controls
with st.sidebar:
    st.header("Параметры поиска")
    top_k = st.slider("Top-K чанков для контекста", min_value=3, max_value=15, value=6)
    use_date_filter = st.checkbox("Фильтр по дате")
    date_from_str: str | None = None
    date_to_str: str | None = None
    if use_date_filter:
        today = date.today()
        df = st.date_input("От", value=date(today.year - 1, today.month, today.day))
        dt = st.date_input("До", value=today)
        date_from_str = df.isoformat()
        date_to_str = dt.isoformat()

    st.divider()
    st.subheader("Примеры вопросов")
    for q in SAMPLE_QUESTIONS:
        if st.button(q, use_container_width=True, key=f"sample-{hash(q)}"):
            st.session_state["query"] = q

# Query input
query = st.text_input(
    "Спроси про митинги:",
    value=st.session_state.get("query", ""),
    placeholder="Например: что решили по архивации событий?",
    key="query",
)

ask = st.button("Найти и ответить", type="primary", disabled=not query.strip())

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if ask and query.strip():
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
    st.subheader("Ответ")
    st.caption(f"Найдено фрагментов: {len(hits)} · поиск занял {search_ms:.0f} мс")

    answer_placeholder = st.empty()

    t_gen = time.perf_counter()
    full_answer = ""
    for piece in _stream_answer(query, hits):
        full_answer += piece
        answer_placeholder.markdown(full_answer)
    gen_ms = (time.perf_counter() - t_gen) * 1000

    st.caption(f"Генерация заняла {gen_ms:.0f} мс")

    if hits:
        st.subheader("Источники")
        for i, h in enumerate(hits, start=1):
            with st.expander(
                f"[{i}] {h.meeting_date or 'без даты'} — {h.title or h.source_path} "
                f"· score={h.score:.3f}"
            ):
                meta_cols = st.columns(3)
                meta_cols[0].markdown(f"**Дата:** {h.meeting_date or '—'}")
                meta_cols[1].markdown(f"**Chunk #:** {h.chunk_index}")
                meta_cols[2].markdown(f"**Score (cosine dist):** {h.score:.4f}")
                st.markdown("**Фрагмент:**")
                st.markdown(f"> {h.snippet}")
                st.caption(f"Источник: `{h.source_path}`")

with st.sidebar:
    st.divider()
    with st.expander("Как это работает"):
        st.markdown(
            """
1. Вопрос эмбеддится через `voyage-3` (`input_type=query`).
2. SQLite + `sqlite-vec` находит K ближайших чанков по cosine distance.
3. Найденные чанки + вопрос подаются в Gemini 2.5 Flash с инструкцией цитировать источники.
4. Ответ стримится в UI, источники раскрываются ниже.

Эмбеддинги документов делаются однократно при ingest'е (`input_type=document`).
Это асимметричное encoding даёт заметно лучшую релевантность, чем общий encoder.
            """
        )
