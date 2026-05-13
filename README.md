# personal-meeting-brain

Local RAG over your personal meeting transcripts, exposed to Claude Code as an MCP server.

## Prerequisites

- macOS (developed and tested on darwin)
- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) for environment and script management
- A [Voyage AI](https://www.voyageai.com/) API key (free tier is sufficient for personal use)

## Setup

```bash
git clone <your-fork> personal-meeting-brain
cd personal-meeting-brain
uv sync
cp .env.example .env
# edit .env and set VOYAGE_API_KEY=...
```

## Ingest transcripts

Drop your meeting notes as `.md` files into `transcripts/` (one file per meeting). Filenames like `2024-08-15_team-sync.md` are recommended — the leading `YYYY-MM-DD` is parsed as the meeting date and the rest becomes the title.

```bash
uv run meeting-brain-ingest
```

Re-running is idempotent: unchanged files are skipped via content-hash. Edited files are re-chunked and re-embedded automatically. Pass `--force` to re-embed everything.

## Register the MCP server with Claude Code

You have two options.

### Option 1: Project-scoped (committed)

This repo ships a `.mcp.json` at the project root. From inside the repo, Claude Code will auto-discover it on launch. No further setup needed.

### Option 2: User-scoped (works from any directory)

```bash
claude mcp add meeting-brain -- uv --directory /Users/denis/AiProjects/personal-meeting-brain run meeting-brain-mcp
```

Adjust the `--directory` path if you cloned the repo elsewhere.

## Try it in Claude

Once registered, ask Claude Code things like:

- "What did we discuss about the search ranker?"
- "List my meetings from this month."
- "Reindex the transcripts folder."
- "Pull up the full transcript for the 2024-08-15 sync."

Claude will pick from four tools:

- `search_meetings` — semantic search over chunks
- `get_meeting` — fetch a full transcript by path or id
- `list_meetings` — browse metadata
- `reindex` — rescan the transcripts folder

There is also a `meetings://index` resource that returns a markdown table of every indexed meeting.

## Schema reference

See [`src/meeting_brain/db.py`](src/meeting_brain/db.py) for the full SQLite schema. Three tables:

- `meetings` — one row per source file, with `raw_text` and metadata
- `chunks` — token-windowed chunks (≈512 tokens, 64-token overlap)
- `vec_chunks` — `sqlite-vec` virtual table holding 1024-dim embeddings

## Embeddings

Embeddings come from Voyage AI's `voyage-3` model (1024 dimensions, multilingual). Documents are embedded with `input_type="document"` at ingest time; queries with `input_type="query"` at search time. This asymmetric encoding gives noticeably better retrieval than treating queries as documents.
