# Orange Memory Fabric

Orange is a memory fabric for developer and agentic workflows. It captures completed sessions from tools like Cursor, Claude Code, MCP, Slack-style chats, Gmail-style threads, and the demo chat, extracts durable memory, stores it in graph/vector form, and retrieves relevant past context when a similar session happens later.

Live demo: [https://site-sage-eta-18.vercel.app](https://site-sage-eta-18.vercel.app)

Backend API: [https://orange-api-production.up.railway.app](https://orange-api-production.up.railway.app)

## Core Loop

```text
SessionIngestionRequest
-> normalize session/messages/profile metadata
-> wait until the session is marked done
-> triage whether anything is worth storing
-> extract durable Insights
-> write Session + Insight graph nodes to Neo4j
-> write searchable vectors to Chroma
-> retrieve prior context with ping_context
```

The most important product loop is:

```text
capture session -> extract memory -> store graph/vector -> retrieve context later
```

## What It Does

- Stores unified `Insight` nodes instead of separate Problem/Solution nodes for new writes.
- Runs extraction only when a user marks a conversation done.
- Uses a Triage Agent to avoid storing generic or low-value chats.
- Extracts engineering insights, user facts, company facts, preferences, and steering.
- Keeps private user memory scoped by email.
- Keeps shared company knowledge scoped by company/org so different companies do not connect.
- Stores graph memory in Neo4j and semantic retrieval memory in Chroma.
- Stores normalized sessions, messages, users, organizations, and memory jobs in Supabase/Postgres scaffolding.
- Exposes retrieval and inspection through MCP tools and FastAPI routes.
- Ships a polished Next.js demo site with chat, graph visualization, and source-app memory map.

## Memory Scopes

Orange treats memory as two related but separate graphs:

```text
Same completed session
       |
       |-> User memory
       |   raw/private context, keyed by user email
       |
       |-> Company memory
           shared facts/incidents, keyed by company/org
```

User memory can store personal details, preferences, website steering, and private debugging history. Company memory should store only durable facts useful to coworkers in the same company, such as internal workflow facts, incident causes, tool decisions, or org-specific technical context.

Examples:

- User memory: "Harsh prefers the Orange homepage to explain app connectors visually, not as node-type cards."
- User memory: "Website steering chats should be remembered privately, not shared globally."
- Company memory: "The company uses `.md` files as the source format for memory."
- Company memory: "AWS Glue issue caused this class of pipeline failure."

## Core Components

### Ingestion + Normalization

- `core/ingestion/session.py` normalizes session payloads, messages, timestamps, profile metadata, `user_email`, company/org identity, source URL, and client/tool metadata.
- Demo completion starts from the frontend and posts the finished conversation to the backend through `POST /demo/complete`.

### Extraction Pipeline

- `core/agents/triage/` decides whether a completed conversation produced anything worth storing.
- `core/agents/insight_extractor/` extracts the minimum set of durable `Insight` nodes from the full session transcript.
- `core/agents/pii_scrubber/` cleans transcripts before company/shared extraction.
- `core/agents/orchestrator.py` runs the completed-session pipeline.

Legacy `issue_agent` and `solution_agent` folders are still present for reference and backwards compatibility, but the new completed-session pipeline writes `Insight` nodes.

### Persistence Layer

- `core/graph_upsert/writer.py` writes `Session` and `Insight` nodes plus relationships into Neo4j.
- `core/graph_upsert/embeddings.py` builds embedding strings for Chroma.
- `core/graph_upsert/dedup.py` manages Chroma collections and similarity checks.
- `core/storage/supabase_store.py` stores durable metadata in Supabase/Postgres when configured.
- `core/graph_schema_v2.py` defines graph-facing data models, including `Insight`.

Current vector collections:

```text
orange_user_vectors
orange_global_vectors
```

Company/shared vectors are scoped by company/org metadata so one company's graph does not bleed into another company's retrieval.

### Retrieval + Inspection

- `core/mcp_server/server.py` exposes MCP tools such as `ping_context`, `store_session`, `inspect_graph`, `get_node`, and `chroma_peek`.
- `core/mcp_server/handlers.py` contains the MCP tool handlers and retrieval logic.
- `core/viz_api/routes/demo.py` exposes demo-facing `POST /demo/complete` and `POST /demo/ping_context`.
- `core/viz_api/routes/graph.py` serves graph read endpoints used by the demo.
- `core/viz_api/routes/chroma.py` serves vector-store inspection endpoints.
- `core/viz_api/routes/health.py` provides lightweight and deep health checks.

### Frontend Demo

The Next.js site lives in `site/`.

It includes:

- Orange landing/demo page
- connected source-app memory map
- animated live contract code block
- profile collection using email and company as the important identity fields
- demo chat with streaming responses
- "Mark conversation done" action that triggers backend storage
- graph visualization with `My Memory` and `Global` scope views
- retrieval chips showing whether context came from private or shared memory

## Repository Layout

```text
.
├── core/
│   ├── agents/
│   │   ├── insight_extractor/
│   │   ├── pii_scrubber/
│   │   └── triage/
│   ├── graph_queries/
│   ├── graph_upsert/
│   ├── ingestion/
│   ├── mcp_server/
│   └── viz_api/
├── site/
│   └── src/
├── scripts/
├── supabase/
├── tests/
├── DEPLOY.md
├── railway.toml
└── requirements.txt
```

## Quick Start

### 1. Create a Python environment

```bash
python3.11 -m venv venv311
source venv311/bin/activate
```

### 2. Install backend dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Important variables:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `CHROMA_PATH`
- `ALLOWED_ORIGINS`
- optional `SUPABASE_DB_URL` or `POSTGRES_DSN`
- optional `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN`

For local frontend-to-backend calls, set:

```text
ORANGE_BACKEND_URL=http://localhost:8001
```

For Vercel production, `ORANGE_BACKEND_URL` should point at the Railway backend.

## Running Locally

### Start the FastAPI backend

```bash
PYTHONPATH=. uvicorn core.viz_api.main:app --reload --port 8001
```

Useful endpoints:

- `GET /health`
- `GET /health/deep`
- `GET /graph/full`
- `GET /graph/nodes`
- `GET /chroma/status`
- `GET /chroma/peek?limit=5`
- `POST /demo/complete`
- `POST /demo/ping_context`

### Start the Next.js demo

```bash
cd site
npm install
npm run dev -- -p 3004
```

Open:

```text
http://localhost:3004
```

### Start the MCP server

```bash
PYTHONPATH=. python -m core.mcp_server.server
```

This runs Orange in stdio mode for MCP-compatible clients.

## MCP Tools

The MCP server currently exposes:

- `ping_context`
- `store_session`
- `resolve_problem`
- `inspect_graph`
- `get_node`
- `get_session_graph`
- `list_sessions`
- `chroma_peek`

`resolve_problem` remains for compatibility; the current memory write path is session-level Insight extraction.

## Deployed Demo

Frontend:

```text
https://site-sage-eta-18.vercel.app
```

Backend:

```text
https://orange-api-production.up.railway.app
```

The Vercel site calls the Railway backend through `ORANGE_BACKEND_URL`. If that variable is absent, the demo graph can fall back to in-memory demo data, but real persistence requires Railway + Neo4j + Chroma.

See `DEPLOY.md` for Railway/Vercel setup details, including Chroma volume persistence.

## Supabase Schema

Orange keeps durable metadata separate from the graph/vector stores. The Supabase migration in `supabase/migrations/` creates a private `orange` schema with:

- `organizations`
- `users`
- `organization_members`
- `source_accounts`
- `session_ingestions`
- `session_messages`
- `memory_write_jobs`

The schema enables RLS and revokes browser-facing `anon`/`authenticated` access. Use server-side database credentials for this path until product-facing policies are intentionally designed.

## Testing

Focused checks used during current development:

```bash
PYTHONPATH=. pytest tests/test_insight_pipeline.py tests/test_mcp_handlers.py tests/test_graph_upsert_v2_writer.py tests/test_ingestion_normalization.py
```

Frontend checks:

```bash
cd site
npm run lint
npm run build
```

Full pytest is not fully clean yet because some legacy tests still import older modules or run live pipeline work during collection.

## Security Notes

- Do not commit secrets.
- `.env`, local databases, Chroma stores, generated inspection exports, and local app artifacts should stay ignored.
- Shared/company memory must not expose contributor emails or private user details.
- Global/company retrieval must remain scoped by company/org identity.
- Use `.env.example` as the local configuration template.

## Roadmap-Friendly Areas

- Make `store_session` async with `memory_write_jobs`
- Add `get_job_status(job_id)`
- Tighten auth and user identity before real org usage
- Improve extraction observability and benchmarks
- Clean or delete legacy tests/imports
- Expand source connectors beyond the demo UI
- Improve company-scoped graph persistence and admin inspection
