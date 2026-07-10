# Orange MCP

Orange exposes **one** Streamable HTTP MCP resource for every client:

```text
https://orange-api-x38s.onrender.com/mcp
```

(Replace with your Render service hostname after deploy.)

There are no separate servers for Grok, Claude, ChatGPT, or other agents. The
backend is provider-neutral. Remote access uses Supabase OAuth Server discovery,
dynamic client registration, PKCE, browser login, and consent. Users do not
create or paste an Orange token.

Setup UI: [Connect Orange](https://site-sage-eta-18.vercel.app/mcp)

Helper (prints provider-specific steps; only Grok mutates local config):

```bash
python scripts/configure_mcp.py url
python scripts/configure_mcp.py grok remote
# remote defaults to name orange-remote; --name must precede remote:
# python scripts/configure_mcp.py grok --name orange-remote remote
python scripts/configure_mcp.py claude
python scripts/configure_mcp.py chatgpt
python scripts/configure_mcp.py generic
```

## Grok CLI

```bash
# Default remote onboarding name is orange-remote (does not overwrite local stdio orange):
grok mcp add --scope user --transport http orange-remote \
  https://orange-api-x38s.onrender.com/mcp

# Production entry (only after remote login and tools work):
grok mcp remove orange
grok mcp add --scope user --transport http orange \
  https://orange-api-x38s.onrender.com/mcp
```

Then open Grok, run `/mcps`, select the server, and press `i`. Complete the
browser email login and approve access. Grok stores and refreshes credentials.

```bash
python scripts/configure_mcp.py grok remote
python scripts/configure_mcp.py grok --name orange-remote remote
# historical alias still works:
python scripts/configure_grok_mcp.py remote
```

See [GROK.md](GROK.md) for troubleshooting and local stdio diagnostics.

## Claude Code / Claude.ai

```bash
claude mcp add --transport http orange https://orange-api-x38s.onrender.com/mcp
```

Or in `.mcp.json` / Claude desktop config (no `Authorization` header):

```json
{
  "mcpServers": {
    "orange": {
      "type": "http",
      "url": "https://orange-api-x38s.onrender.com/mcp"
    }
  }
}
```

Claude.ai custom connectors use the same URL. Complete browser OAuth when
prompted; do not paste a bearer token.

```bash
python scripts/configure_mcp.py claude
```

## ChatGPT (Developer mode — not Custom GPT Actions)

Orange connects through ChatGPT **Developer mode** as a **developer-mode App**
for a remote MCP server (SSE or streaming HTTP). This is not Custom GPT Actions.

Official docs:
[Developer mode](https://developers.openai.com/api/docs/guides/developer-mode) ·
[Help center](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt)

1. Enable **Developer mode** in ChatGPT web: **Settings → Security and login**
   (or **Settings → Apps → Advanced Settings**). Workspace admins may need to
   allow this on Business/Enterprise/Edu first.
2. Open **Settings → Plugins** ([chatgpt.com/plugins](https://chatgpt.com/plugins))
   or **Apps → Create**. Use **+** to create a developer-mode app (only after
   Developer mode is on).
3. Paste the Orange MCP URL, choose **OAuth** (not a static secret), click
   **Scan Tools**, complete browser login/consent, then **Create**.
4. In a chat, open the Plus menu → **Developer mode** → select the Orange app.

```text
https://orange-api-x38s.onrender.com/mcp
```

```bash
python scripts/configure_mcp.py chatgpt
```

## Generic MCP clients

Any Streamable HTTP client that supports OAuth protected resources:

1. Point the client at `https://orange-api-x38s.onrender.com/mcp`.
2. Allow discovery of `/.well-known/oauth-protected-resource/mcp`.
3. Complete dynamic client registration and PKCE browser login.
4. Use the memory protocol tools below.

Do not put a static bearer token in config. Orange does not ship client secrets.

```bash
python scripts/configure_mcp.py generic
```

## Memory protocol

1. Call `recall_memory` before substantial work.
2. Call `checkpoint_context` when an important finding should survive a crash.
3. Call `complete_conversation` once, at the end of a useful session.
4. If the write is queued, use `get_job_status` until it succeeds.

`complete_conversation` returns quickly on the hosted backend because the
transcript is persisted first and extraction runs through a leased Postgres
job. A process restart cannot lose an accepted job.

Nodes written through any MCP client bump the scoped graph version. The Orange
UI polls that version and refreshes automatically so new nodes appear without a
manual reload.

## Tools and annotations

| Tool | Kind | Annotation hints |
|------|------|------------------|
| `orange_status` | read | `readOnlyHint`, non-destructive, idempotent |
| `recall_memory` | read | `readOnlyHint`, non-destructive, idempotent |
| `inspect_graph` | read | `readOnlyHint`, non-destructive, idempotent |
| `get_node` | read | `readOnlyHint`, non-destructive, idempotent |
| `get_session_graph` | read | `readOnlyHint`, non-destructive, idempotent |
| `list_sessions` | read | `readOnlyHint`, non-destructive, idempotent |
| `get_job_status` | read | `readOnlyHint`, non-destructive, idempotent |
| `memory_peek` | read | `readOnlyHint`, non-destructive, idempotent |
| `checkpoint_context` | write | non-destructive write |
| `complete_conversation` | write | non-destructive write |
| `store_session` | write | non-destructive write |

Write tools append durable memory; they do not delete unrelated graph data.

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

Protected-resource metadata points at Supabase Auth. Authorization-server
metadata advertises `registration_endpoint` and
`code_challenge_methods_supported` (PKCE). An unauthenticated MCP request
returns `401` with a `WWW-Authenticate` header containing `resource_metadata`.
OAuth discovery and browser consent routes remain accessible without an MCP
bearer token.

## Local stdio

Local stdio remains available for development:

```bash
export POSTGRES_DSN='postgresql://...'
export OPENAI_API_KEY='...'
export ORANGE_USER_EMAIL='you@example.com'
PYTHONPATH=. python -m core.mcp_server.server
```

```bash
python scripts/configure_mcp.py grok local --email you@example.com
```

Stdio writes process inline by default. The hosted Render service sets
`ORANGE_MEMORY_WRITE_MODE=queued` and runs the durable worker in the API
lifespan. Prefer remote MCP when you need agent writes to appear on the
deployed website graph.
