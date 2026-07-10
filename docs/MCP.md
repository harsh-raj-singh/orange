# Orange MCP

Orange exposes a Streamable HTTP MCP resource at:

```text
https://orange-api-x38s.onrender.com/mcp
```

(Replace with your Render service hostname after deploy.)

Remote access uses Supabase OAuth Server discovery, dynamic client
registration, PKCE, browser login, and consent. Users do not create or paste an
Orange token.

## Grok CLI

```bash
grok mcp remove orange
grok mcp add --scope user --transport http orange \
  https://orange-api-x38s.onrender.com/mcp
```

Then open Grok, run `/mcps`, select Orange, and press `i`. Complete the browser
email login and approve access. Grok stores and refreshes the resulting
credentials.

See [GROK.md](GROK.md) for troubleshooting and local stdio mode.

## Memory protocol

1. Call `recall_memory` before substantial work.
2. Call `checkpoint_context` when an important finding should survive a crash.
3. Call `complete_conversation` once, at the end of a useful session.
4. If the write is queued, use `get_job_status` until it succeeds.

`complete_conversation` returns quickly on the hosted backend because the
transcript is persisted first and extraction runs through a leased Postgres
job. A process restart cannot lose an accepted job.

## Tools

- `orange_status`: Supabase Postgres, pgvector, job, OAuth, and tool health.
- `recall_memory`: scoped pgvector recall with Postgres graph context.
- `checkpoint_context`: immediate lightweight durable Insight.
- `complete_conversation`: preferred end-of-session ingestion.
- `store_session`: lower-level ingestion API.
- `get_job_status`: queued/running/retry/succeeded/dead-letter state and result.
- `inspect_graph`: paginated graph-safe nodes and edges.
- `get_node`: one authorized node and its immediate neighborhood.
- `get_session_graph`: the Session → Insight subgraph.
- `list_sessions`: paginated authorized sessions.
- `memory_peek`: recent graph-safe Insight rows without raw embeddings.

The `orange://instructions` resource contains the same protocol in a form MCP
clients can read directly.

## Identity and isolation

For remote calls, Orange ignores a conflicting client-supplied email and uses
the verified Supabase `sub` and email claims. Private memory is owned by the
internal user mapped to that subject. Company memory additionally requires an
explicit organization membership; supplying a company name does not enroll a
user into an existing company.

The dedicated Orange Supabase project isolates the authorization server and
memory data. Supabase Auth currently does not implement RFC 8707 resource
indicators, so the FastMCP integration cannot audience-bind tokens to `/mcp` at
the protocol level. Dedicated-project isolation and strict issuer/signature/
identity checks mitigate that limitation; it should be revisited when Supabase
adds resource-indicator support.

## Discovery checks

```bash
curl https://orange-api-x38s.onrender.com/.well-known/oauth-protected-resource/mcp
curl https://orange-api-x38s.onrender.com/.well-known/oauth-authorization-server
```

An unauthenticated MCP request should return `401` with a `WWW-Authenticate`
header containing `resource_metadata`. OAuth discovery and browser consent
routes remain accessible without an MCP bearer token.

## Local stdio

Local stdio remains available for development:

```bash
export POSTGRES_DSN='postgresql://...'
export OPENAI_API_KEY='...'
export ORANGE_USER_EMAIL='you@example.com'
PYTHONPATH=. python -m core.mcp_server.server
```

Stdio writes process inline by default. Railway sets
`ORANGE_MEMORY_WRITE_MODE=queued` and runs the durable worker in the API
lifespan.
