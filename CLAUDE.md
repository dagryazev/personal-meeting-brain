# Claude context for personal-meeting-brain

## Purpose

Local RAG over Denis's personal meeting transcripts. SQLite + `sqlite-vec` for storage, Voyage AI `voyage-3` (1024-dim) for embeddings, exposed to Claude Code through a stdio MCP server. Everything runs locally; the only network call is to Voyage for embedding.

## Ingest

```bash
uv run meeting-brain-ingest          # incremental, hash-skips unchanged files
uv run meeting-brain-ingest --force  # re-embed everything
```

Transcripts live in `transcripts/` as `.md` files. Filenames with a leading `YYYY-MM-DD` get that date parsed into `meetings.meeting_date`.

## Query (from Claude Code)

The MCP server is registered via `.mcp.json` at the repo root. Available tools:

- `search_meetings(query, top_k=8, date_from?, date_to?)` — semantic search
- `get_meeting(source_path? | meeting_id?)` — full transcript
- `list_meetings(limit=50, date_from?, date_to?)` — metadata only
- `reindex(force=False)` — rescan transcripts folder

Resource: `meetings://index` — markdown table of all indexed meetings.

## File format

`.md` only. The ingester does `rglob("*.md")` and ignores everything else.

## Key files

- `src/meeting_brain/config.py` — paths, model name, chunk sizes, env loading
- `src/meeting_brain/db.py` — `connect()` returns a `sqlite_vec`-loaded connection with schema applied
- `src/meeting_brain/chunker.py` — token-windowed chunking via `tiktoken`
- `src/meeting_brain/embeddings.py` — `embed_documents` / `embed_query` against Voyage
- `src/meeting_brain/ingest.py` — `ingest_folder`, `ingest_file`, CLI entrypoint
- `src/meeting_brain/search.py` — `search()` → `list[SearchHit]`, KNN via `vec_chunks MATCH`
- `src/meeting_brain/mcp_server.py` — FastMCP server exposing the four tools + the index resource
- `tests/` — pytest suite, all tests use deterministic SHA-based fake embeddings

## Don't

- Don't add cloud deps (no postgres, no pinecone, no qdrant). The whole point is local-first.
- Don't switch DB engines or vector libs. SQLite + `sqlite-vec` is the contract.
- Don't change the schema in `db.py` without writing a migration. There is data in `data/meetings.db`.
- Don't share a single sqlite connection across MCP tool calls; each tool opens its own (sqlite-vec is flaky with shared connections).
- Don't filter inside the `vec0 MATCH` query — sqlite-vec doesn't compose well with WHERE on joined tables. Over-fetch from `vec_chunks`, then filter in Python.
