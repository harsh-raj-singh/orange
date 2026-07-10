# Orange Memory Fabric

Orange is a memory fabric for developer and agentic workflows. It captures completed sessions from tools like Cursor, Claude Code, MCP, Slack recordings, and the demo chat, extracts durable memory, stores it in graph/vector form, and retrieves relevant past context when a similar session happens later.

Live demo: [https://site-sage-eta-18.vercel.app](https://site-sage-eta-18.vercel.app)

Backend API: Render Free web service (`orange-api` — see `DEPLOY.md` / `render.yaml`).
Legacy Railway URL is retired after the trial expired.

## Core Loop

```text
SessionIngestionRequest
-> normalize session/messages/profile metadata
-> wait until the session is marked done
-> triage whether anything is worth storing
-> extract durable Insights
-> atomically write Session + Insight + relationship rows to Supabase Postgres
-> store searchable embeddings in pgvector
-> retrieve prior context with recall_memory
```

The most important product loop is:

```text
capture session -> extract memory -> store graph/vector -> retrieve context later
```

## What It Does

- Stores unified `Insight` nodes as the only active memory node type.
- Runs extraction only when a user marks a conversation done.
- Uses a Triage Agent to avoid storing generic or low-value chats.
- Extracts engineering insights, user facts, company facts, preferences, and steering.
- Keeps private user memory scoped by email.
- Keeps shared company knowledge scoped by company/org so different companies do not connect.
- Stores the graph, semantic vectors, normalized sessions, identities, and durable jobs in one Supabase Postgres database.
- Publishes a cheap per-scope graph version so the deployed UI refreshes when MCP, Slack, or the website writes nodes.
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

Older Problem/Solution extraction code has been retired. The completed-session pipeline writes `Insight` nodes directly.

### Persistence Layer

- `core/storage/supabase_store.py` is the transactional Postgres graph repository.
- `core/storage/embeddings.py` produces `text-embedding-3-small` vectors for pgvector.
- `supabase/migrations/` defines scoped graph tables, ANN indexes, RLS, Realtime, and durable leased jobs.
- `core/graph_schema_v2.py` defines graph-facing data models, including `Insight`.

Private and company embeddings share one indexed table but remain filtered by
their user or organization owner, so one scope cannot bleed into another.

### Retrieval + Inspection

- `core/mcp_server/server.py` exposes OAuth-protected MCP tools such as `recall_memory`, `checkpoint_context`, `complete_conversation`, `get_job_status`, `inspect_graph`, and `get_node`.
- `core/mcp_server/handlers.py` contains the MCP tool handlers and retrieval logic.
- `core/viz_api/routes/demo.py` exposes demo-facing `POST /demo/complete` and `POST /demo/recall_memory`.
- `core/viz_api/routes/graph.py` serves graph read endpoints used by the demo.
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
├── render.yaml
├── Dockerfile.railway
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
- `POSTGRES_DSN`
- `SUPABASE_URL`
- `SUPABASE_JWT_ALGORITHM=ES256`
- `ALLOWED_ORIGINS`
- optional `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN`

For local frontend-to-backend calls, set:

```text
ORANGE_BACKEND_URL=http://localhost:8001
```

For Vercel production, `ORANGE_BACKEND_URL` should point at the Render backend.

## Running Locally

### Start the FastAPI backend

```bash
PYTHONPATH=. uvicorn core.viz_api.main:app --reload --port 8001
```

Useful endpoints:

- `GET /health`
- `GET /health/deep`
- `GET /graph/full`
- `GET /graph/nodes/{node_id}/neighborhood`
- `POST /demo/complete`
- `POST /demo/recall_memory`

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
See [`docs/MCP.md`](docs/MCP.md) for provider-neutral setup (Grok, Claude,
ChatGPT, and generic MCP clients). One remote URL is used for every client.

## MCP Tools

The MCP server currently exposes:

- `orange_status` (read-only)
- `recall_memory` (read-only)
- `checkpoint_context` (non-destructive write)
- `complete_conversation` (non-destructive write)
- `store_session` (non-destructive write)
- `inspect_graph` (read-only)
- `get_node` (read-only)
- `get_session_graph` (read-only)
- `list_sessions` (read-only)
- `get_job_status` (read-only)
- `memory_peek` (read-only)

For coding agents, the happy path is `recall_memory` before answering, `checkpoint_context` when important mid-session context should be preserved, and `complete_conversation` once when the session is done. Nodes written through any MCP client bump the scoped graph version so the UI refreshes automatically.

Desktop setup page (**Connect Orange**):

```text
https://site-sage-eta-18.vercel.app/mcp
```

One Streamable HTTP URL for Grok CLI, Claude Code / Claude.ai, ChatGPT, and
generic MCP clients. Browser OAuth (discovery, PKCE, dynamic client
registration) stores and refreshes credentials in the client. Users do not copy
API keys, bearer tokens, or headers.

```bash
python scripts/configure_mcp.py grok remote
# defaults to orange-remote; --name before remote if overriding:
# python scripts/configure_mcp.py grok --name orange-remote remote
python scripts/configure_mcp.py claude
python scripts/configure_mcp.py chatgpt   # ChatGPT Developer mode App, not Custom GPT Actions
python scripts/configure_mcp.py generic
```

## Deployed Demo

Frontend:

```text
https://site-sage-eta-18.vercel.app
```

Backend:

```text
https://orange-api-x38s.onrender.com
```

(Replace with your Render service hostname after the first deploy.)

The Vercel site calls Render through `ORANGE_BACKEND_URL` and forwards the
signed-in user's Supabase access token. Signed-out visitors may see preview data;
real user memory is never selected by an unverified browser email.

See `DEPLOY.md` for Supabase/Render/Vercel setup and the provider-neutral MCP
OAuth smoke test (Grok → Claude → ChatGPT).

## Supabase Schema

Orange keeps the entire durable memory path in the private Supabase `orange` schema:

- `organizations`
- `users`
- `organization_members`
- `source_accounts`
- `session_ingestions`
- `session_messages`
- `memory_write_jobs`
- `memory_sessions`
- `insights` (including pgvector embeddings)
- `memory_edges`
- `graph_scope_versions`

The backend owns writes. Authenticated reads are protected by RLS and verified
Supabase identity/organization membership.

## Testing

Backend checks:

```bash
PYTHONPATH=. pytest -q tests
```

Frontend checks:

```bash
cd site
npm run lint
npm run build
```

## Security Notes

- Do not commit secrets.
- `.env`, local databases, generated inspection exports, and local app artifacts should stay ignored.
- Shared/company memory must not expose contributor emails or private user details.
- Global/company retrieval must remain scoped by company/org identity.
- Use `.env.example` as the local configuration template.

## Next Areas

- Add organization invitation/admin workflows around the existing membership checks.
- Add extraction-quality benchmarks and long-term pgvector recall evaluation.
- Expand source connectors beyond MCP, Slack, and the demo UI.
- Add an admin-only dead-letter job replay surface.
