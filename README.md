# Personal Meeting Brain

> Local RAG over your meeting transcripts. Runs entirely on your laptop. Exposed to Claude Code as an MCP server, with an optional web demo.

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)
![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)
![Local-first](https://img.shields.io/badge/local--first-yes-orange.svg)

<!-- TODO: replace with a 15–25s GIF showing a query in Claude Code → MCP tool call → answer with citations. Save as demo/claude-mcp-demo.gif -->
![Claude Code MCP demo](demo/claude-mcp-demo.gif)

---

## Why I built this

I run 5–10 standups and technical calls a week. Two weeks later I can't remember what we decided about rate limits, which blocker Andrey mentioned twice, or what I promised to ship by Friday. Existing meeting tools record everything beautifully — and then forget it across meetings.

So I built a small, local, no-SaaS system that does one thing well: **answer questions across all of my transcripts**, with citations, from inside the tool I already use to think (Claude Code).

It's a pet project. But the engineering choices are the same ones I'd make in production.

---

## What it does

Drop your meeting transcripts into a folder as Markdown files. The system:

1. **Ingests and chunks** them (token-windowed, content-hash idempotent — re-running is safe).
2. **Embeds** each chunk with Voyage AI's `voyage-3` (1024-dim, multilingual, asymmetric query/document encoding).
3. **Stores** vectors and metadata in a single SQLite file (`sqlite-vec` for ANN search).
4. **Exposes** four tools over [MCP](https://modelcontextprotocol.io): `search_meetings`, `get_meeting`, `list_meetings`, `reindex`.
5. **Plugs into Claude Code** so you can ask "What did we decide about domain check limits?" in the same window where you write code.

A self-contained Streamlit + Gemini demo is included for showing the retrieval loop to people who don't have Claude Code installed.

---

## Quick start

```bash
git clone https://github.com/dagryazev/personal-meeting-brain
cd personal-meeting-brain
uv sync
cp .env.example .env
# add VOYAGE_API_KEY (free tier is enough) and GEMINI_API_KEY (for the demo)

# Drop your *.md transcripts into transcripts/ (filename like 2024-08-15_team-sync.md)
uv run meeting-brain-ingest

# Option A — register as an MCP server in Claude Code
claude mcp add meeting-brain -- uv --directory $(pwd) run meeting-brain-mcp

# Option B — run the web demo locally
uv run streamlit run demo/app.py
```

That's it. Ask Claude Code: *"What did we discuss about the search ranker last week?"*

---

## Try it live

A public demo runs on Railway with 8 fictional transcripts (made-up startup, invented people):

**[personal-meeting-brain-production.up.railway.app](https://personal-meeting-brain-production.up.railway.app/)**

The demo is intentionally minimal — Streamlit, no auth, public dataset. The **real** interface is the MCP server inside Claude Code; the web app exists so you can see the retrieval loop end-to-end without installing anything.

<!-- TODO: replace with a 20s GIF of the Streamlit demo answering a question with sources expanded. Save as demo/streamlit-demo.gif -->
![Streamlit demo](demo/streamlit-demo.gif)

---

## Architecture

```mermaid
flowchart LR
    subgraph Ingest
        T[Markdown<br/>transcripts/] --> P[Parse +<br/>token-windowed<br/>chunking]
        P --> H[Content-hash<br/>idempotency check]
        H --> E[Voyage AI<br/>document embeddings]
    end

    subgraph Storage
        E --> M[(SQLite:<br/>meetings)]
        E --> C[(SQLite:<br/>chunks)]
        E --> V[(sqlite-vec:<br/>1024-dim vectors)]
    end

    subgraph Query
        Q1[Claude Code<br/>via MCP] --> R[Voyage query<br/>embedding]
        Q2[Streamlit demo] --> R
        R --> S[Vector search<br/>over sqlite-vec]
        S --> A[Top-k chunks<br/>+ metadata]
        A --> G[Gemini /<br/>Claude Code]
        G --> O[Answer with<br/>cited sources]
    end
```

Single SQLite file. No external services beyond the embedding and generation APIs. Survives a `scp` to another machine — that was a design goal, not an accident.

---

## Engineering decisions

The interesting parts of this project aren't the LLM calls. They're the trade-offs I made along the way.

### SQLite + `sqlite-vec` instead of Postgres + pgvector

A single-file database for a single-user system is the right answer. No Docker for the DB, no managed service, no migrations to wrangle. The whole index is ~5–20 MB per few hundred meetings — small enough to back up, sync, or rebuild from scratch.

`sqlite-vec` is a recent extension that ships ANN search inside SQLite with no extra processes. For datasets in the thousands of chunks, it's faster to set up than pgvector and indistinguishable in retrieval quality.

*Reconsider when:* multi-user write contention, or chunk counts above ~100k.

### Voyage AI `voyage-3` for embeddings

1024 dimensions, multilingual (my meetings mix English and Russian — most providers degrade noticeably on the second language). Better retrieval on technical/conversational text than `text-embedding-3-small` in my informal evals, at competitive cost.

Free tier is enough for personal use (200M tokens/month at time of writing).

### Asymmetric query/document encoding

Documents are embedded with `input_type="document"` at ingest; queries with `input_type="query"` at search time. Voyage's docs are explicit that this materially improves retrieval — same model, different prefix, noticeably better top-k. It's the kind of detail naive RAG implementations skip and then wonder why their retrieval is mediocre.

### Token-windowed chunking (~512 tokens, 64-token overlap)

Meeting transcripts are conversational and bursty. Fixed-size chunks at 512 tokens with 64-token overlap preserve enough context per chunk to be self-contained, without diluting embeddings across multiple topics.

This is a deliberate v1 simplification. Speaker-aware chunking (grouping by utterance/exchange) is on the roadmap and would likely lift retrieval precision another 5–10%.

### Content-hash idempotent ingest

Each transcript's SHA-256 is stored. Re-running ingest skips unchanged files and re-embeds only edited ones. Safe to run on a cron, on a file watcher, or every time you launch the MCP server. Tiny detail, but it's the difference between "demo script" and "tool I actually use daily."

### MCP exposure as the primary interface

This is the project's biggest bet. Instead of building yet another chat UI, the retrieval lives behind four tools (`search_meetings`, `get_meeting`, `list_meetings`, `reindex`) and one resource (`meetings://index`). Claude Code becomes the front end — full multi-turn reasoning, citations, code generation, all for free.

The Streamlit demo exists for people who can't run Claude Code. It's not the product.

---

## Performance & cost

<!-- TODO: replace with real numbers after running evals/run_evals.py. Keep the format. -->

| Metric                          | Value      | Notes                                  |
| ------------------------------- | ---------- | -------------------------------------- |
| Recall@5 on eval set            | TBD        | 30 hand-written queries over 8 meetings |
| MRR@10                          | TBD        |                                        |
| Query latency, P50              | TBD ms     | embedding + vector search + Gemini     |
| Query latency, P95              | TBD ms     |                                        |
| Ingest time per meeting         | TBD s      | parse + chunk + embed (Voyage)         |
| Cost per query                  | $TBD       | Voyage query + Gemini generation       |
| Cost per ingested meeting       | $TBD       | Voyage doc embeddings only             |
| Index size, 100 meetings        | TBD MB     | SQLite file on disk                    |

Reproduce with:

```bash
uv run python -m meeting_brain.evals
```

---

## MCP integration

Once registered with Claude Code, four tools become available:

- **`search_meetings(query, limit=5)`** — semantic search over chunks. Returns ranked excerpts with meeting metadata.
- **`get_meeting(meeting_id | path)`** — fetch the full transcript.
- **`list_meetings(limit=50, offset=0)`** — browse metadata.
- **`reindex(force=False)`** — rescan `transcripts/` for new or edited files.

Plus one resource:

- **`meetings://index`** — a Markdown table of every indexed meeting, suitable for dropping into Claude's context.

Example prompts that work well:

> *"What did we decide about the domain-check rate limits?"*
> *"Pull up the full transcript of the team sync on Aug 15."*
> *"List my meetings from this month and summarise what each one was about."*
> *"Reindex the transcripts folder — I just added two new files."*

---

## Project structure

```
personal-meeting-brain/
├── src/meeting_brain/      # ingestion, embeddings, search, MCP server
├── demo/                   # Streamlit app + Dockerfile bits + screenshots
├── transcripts/            # your *.md files go here (or use the bundled fictional ones)
├── data/                   # SQLite database (gitignored)
├── tests/                  # pytest suite
├── .mcp.json               # project-scoped MCP config for Claude Code
├── Dockerfile              # multi-stage, uv-based, deploys cleanly to Railway
├── railway.toml            # Railway service configuration
└── pyproject.toml          # uv-managed dependencies
```

---

## Data schema

Three tables, defined in [`src/meeting_brain/db.py`](src/meeting_brain/db.py):

- **`meetings`** — one row per source file. `id`, `path`, `title`, `meeting_date`, `raw_text`, `content_hash`, `ingested_at`.
- **`chunks`** — token-windowed chunks. `id`, `meeting_id`, `chunk_index`, `text`, `start_token`, `end_token`.
- **`vec_chunks`** — `sqlite-vec` virtual table, `1024-dim` float vectors keyed on `chunks.id`.

---

## Roadmap

This is a pet project, but it's actively used. Things on the bench:

- **Hybrid search** (BM25 via SQLite FTS5 + dense vectors with reciprocal rank fusion). Personal meetings are full of names and technical acronyms that pure semantic search loses.
- **Speaker-aware chunking** instead of fixed-size windows.
- **Action item & decision extraction** as a separate pass, stored in their own table and exposed as MCP tools (`find_decisions`, `list_action_items`).
- **People aggregation** — auto-build per-person summaries that update after each new meeting, for pre-meeting briefings.
- **Focus tracking** — surface "what I've been spending my brain on lately" across the last N standups.
- **Direct ClickUp ingest** as an alternative to the Markdown folder, since that's where my real transcripts live.

Not on the roadmap: turning this into a SaaS, joining your meetings as a bot, or anything that ships my conversations to a server I don't own.

---

## Local-first, by design

- No data leaves your machine except embedding API calls (Voyage) and generation API calls (Gemini, optional).
- The full index is a single SQLite file. Back it up by copying one file. Sync between machines by `scp`.
- The MCP server runs locally; Claude Code talks to it over stdio.
- The Streamlit demo on Railway exists only for the public showcase with fictional data.

---

## License

MIT. Do whatever you want with the code. The bundled transcripts are entirely fictional.

---

## Acknowledgments

- [`sqlite-vec`](https://github.com/asg017/sqlite-vec) by Alex Garcia — the quiet workhorse of this project.
- [Voyage AI](https://www.voyageai.com/) for `voyage-3` and the asymmetric encoding API.
- [Anthropic's MCP](https://modelcontextprotocol.io) for making "tool" a first-class citizen in Claude Code.