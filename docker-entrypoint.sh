#!/usr/bin/env bash
# Container entrypoint: (re)index transcripts, then launch Streamlit.
#
# Idempotent — ingest_folder skips unchanged files via content_hash, so on
# subsequent boots (with a persistent volume) nothing is re-embedded.

set -euo pipefail

echo "[entrypoint] indexing transcripts in ${MEETING_BRAIN_TRANSCRIPTS_DIR}"
if [ -z "${VOYAGE_API_KEY:-}" ]; then
  echo "[entrypoint] WARN: VOYAGE_API_KEY is not set — ingest will fail. Skipping." >&2
else
  meeting-brain-ingest || {
    echo "[entrypoint] WARN: ingest exited non-zero, continuing to serve." >&2
  }
fi

echo "[entrypoint] launching Streamlit on 0.0.0.0:${PORT:-8080}"
exec streamlit run demo/app.py \
  --server.address=0.0.0.0 \
  --server.port="${PORT:-8080}" \
  --server.headless=true \
  --browser.gatherUsageStats=false
