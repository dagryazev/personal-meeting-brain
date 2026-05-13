# syntax=docker/dockerfile:1.7

# ---------- Stage 1: build virtualenv with uv -------------------------------
FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first (cached as long as pyproject.toml / uv.lock don't change).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Install the project itself.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# ---------- Stage 2: runtime ------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    MEETING_BRAIN_TRANSCRIPTS_DIR=/app/transcripts \
    MEETING_BRAIN_DB_PATH=/app/data/meetings.db \
    PORT=8080

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src ./src
COPY demo ./demo

# Bundle demo transcripts into the image so the container can self-bootstrap
# without any external mount. On Railway, /app/data is mounted as a volume
# (persistent SQLite); /app/transcripts stays read-only inside the image.
RUN mkdir -p /app/transcripts /app/data \
    && cp -r /app/demo/transcripts/. /app/transcripts/

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/app/docker-entrypoint.sh"]
