#!/usr/bin/env bash
# Container entrypoint: launch Streamlit immediately, index transcripts in
# the background. This keeps the Railway healthcheck (/_stcore/health) from
# timing out while Voyage rate-limit backoffs run on a cold start.
#
# ingest_folder is idempotent — it skips unchanged files via content_hash,
# so on subsequent boots (with a persistent volume) the background ingest
# is a no-op.

set -euo pipefail

if [ -z "${VOYAGE_API_KEY:-}" ]; then
  echo "[entrypoint] WARN: VOYAGE_API_KEY is not set — skipping background ingest." >&2
else
  (
    echo "[entrypoint] background-indexing transcripts in ${MEETING_BRAIN_TRANSCRIPTS_DIR}"
    meeting-brain-ingest || echo "[entrypoint] WARN: ingest exited non-zero." >&2
  ) &
fi

echo "[entrypoint] launching Streamlit on 0.0.0.0:${PORT:-8080}"
exec streamlit run demo/app.py \
  --server.address=0.0.0.0 \
  --server.port="${PORT:-8080}" \
  --server.headless=true \
  --browser.gatherUsageStats=false
