# Orange MCP Setup

Orange exposes a local stdio MCP server for coding agents. The intended loop is:

```text
agent starts work
  -> recall_memory(query, user_email)
  -> use returned memory while answering
agent finds an important decision/root cause/non-obvious fix
  -> checkpoint_context(note, user_email)
agent reaches final answer / user says done
  -> complete_conversation(transcript or messages, user_email, summary/key_entities/decisions/problems_solved)
  -> Orange triages and writes Insight nodes
```

The durable extraction write path is session-level. `checkpoint_context` is a lightweight Neo4j-only safety marker for important mid-session context. The agent calls `complete_conversation` once when the session is meaningfully done.

## Conversation Completion Rule

## Orange Memory Protocol

### START of every session
Call recall_memory with a short query describing the current task before 
doing any work. This hydrates context from prior sessions.

### DURING a session
Call checkpoint_context whenever:
- A non-obvious solution is found
- An important architectural decision is made
- A root cause is identified
Do NOT call complete_conversation mid-session.

### END of session (final answer given, or user says done/remember/store/wrap)
Call complete_conversation with transcript or messages.
- Provide summary, key_entities, decisions, problems_solved if possible.
- Set worth_storing=false for trivial sessions (greetings, generic Q&A, 
  one-off lookups with no durable content).
- Leave worth_storing unset to let Orange triage decide automatically.
- This must be the LAST tool call before ending the response.

### Identity
Always pass user_email when available. For org/company memory, pass company 
or org_id. If using a remote MCP token, user_email is inferred automatically.

Orange still runs triage after completion unless `worth_storing=true` is supplied. If the session has no durable memory, `complete_conversation` returns `skipped_reason` and writes no nodes.

## Tools

- `orange_status`: verifies Neo4j, Chroma, auth, schema labels, and frontend/backend Neo4j alignment.
- `recall_memory`: retrieves private user memory and company-scoped shared memory before answering.
- `checkpoint_context`: writes a lightweight Neo4j-only checkpoint mid-session.
- `complete_conversation`: preferred final write tool for Claude Code, Codex, Cursor, and other MCP clients.
- `store_session`: low-level ingestion tool kept for compatibility.
- `inspect_graph`, `get_node`, `get_session_graph`, `list_sessions`, `chroma_peek`: inspection/debugging tools.
- `resolve_problem`: legacy compatibility tool for old Problem/Solution graphs.

## Prerequisites

From the repo root:

```bash
python3.11 -m venv venv311
source venv311/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Required `.env` values for real writes:

```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.4-nano
NEO4J_URI=bolt://...
FRONTEND_NEO4J_URI=bolt://... # optional, for orange_status alignment checks
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
CHROMA_PATH=./chroma_db
```

For now, treat personal email as the identity key. The server can read it from:

1. explicit `user_email` in the tool call
2. a signed self-serve MCP token minted after Google sign-in at `/mcp/connect`
3. bearer-token mapping in `ORANGE_MCP_TOKEN_EMAILS`
4. local fallback `ORANGE_USER_EMAIL`

Codex and Claude Code do not currently expose the signed-in account email to arbitrary MCP servers in a reliable server-side field. I verified the local Codex config on this device: `~/.codex/config.toml` contains MCP settings but no account email, and `auth.json` stores auth tokens without a readable email field. That means Orange should not depend on the client login email until we add OAuth.

## Run Locally

```bash
PYTHONPATH=. python -m core.mcp_server.server
```

The process speaks MCP over stdio by default, so it will wait for an MCP client to connect.

## Remote MCP

The Railway/FastAPI backend also mounts Orange MCP at:

```text
https://orange-api-production.up.railway.app/mcp/
```

Remote MCP uses Streamable HTTP and bearer-token auth. Set one of these on Railway:

Self-serve website tokens:

```bash
railway variables set ORANGE_MCP_SIGNING_SECRET=$(openssl rand -hex 32)
railway variables set ORANGE_PUBLIC_BACKEND_URL=https://orange-api-production.up.railway.app
railway variables set GOOGLE_CLIENT_ID=your-google-web-client-id.apps.googleusercontent.com
```

Set the same Google web client id on Vercel:

```text
NEXT_PUBLIC_GOOGLE_CLIENT_ID=your-google-web-client-id.apps.googleusercontent.com
```

Then users can open:

```text
https://site-sage-eta-18.vercel.app/mcp
```

They continue with Google, Orange verifies the Google ID token server-side, then returns a signed bearer token and copyable Codex config.

Single-user/default token:

```bash
railway variables set ORANGE_MCP_BEARER_TOKEN=replace-with-random-token
railway variables set ORANGE_USER_EMAIL=harsh@example.com
```

Multi-user token-to-email mapping:

```bash
railway variables set 'ORANGE_MCP_TOKEN_EMAILS={"token-for-harsh":"harsh@example.com","token-for-teammate":"teammate@example.com"}'
```

With `ORANGE_MCP_TOKEN_EMAILS`, users do not need to pass `user_email` manually; the MCP request token maps to their private email identity. Use long random tokens. Anyone with a token can write to that mapped user's memory.

The same app still serves REST endpoints for the Vercel site, so MCP-written Neo4j nodes are visible to the deployed graph as long as Railway and the MCP server use the same Neo4j database.

Current security note: `/mcp/connect` verifies a Google ID token before minting an Orange MCP token. This is good enough for the desktop beta. Full MCP OAuth can replace the token-copy flow later, using Codex's `codex mcp login <server-name>` path.

## Claude Code Remote

```bash
claude mcp add --transport http --scope user orange \
  https://orange-api-production.up.railway.app/mcp/ \
  --header "Authorization: Bearer YOUR_ORANGE_MCP_TOKEN"
```

Then run `/mcp` inside Claude Code and verify the `orange` server is connected.

## Claude Code Local

Claude Code supports local stdio MCP servers with `claude mcp add`. Replace paths with your machine's repo path:

```bash
ORANGE_ROOT=/absolute/path/to/orange
ORANGE_PYTHON="$ORANGE_ROOT/venv311/bin/python"

claude mcp add --scope user --transport stdio --env PYTHONPATH="$ORANGE_ROOT" orange \
  -- "$ORANGE_PYTHON" -m core.mcp_server.server

claude mcp list
```

Inside Claude Code, run `/mcp` to confirm the `orange` server is connected. Then ask Claude to call `orange_status`.

Project-scoped `.mcp.json` form:

```json
{
  "mcpServers": {
    "orange": {
      "type": "stdio",
      "command": "${ORANGE_PYTHON:-/absolute/path/to/orange/venv311/bin/python}",
      "args": ["-m", "core.mcp_server.server"],
      "env": {
        "PYTHONPATH": "${ORANGE_ROOT:-/absolute/path/to/orange}"
      }
    }
  }
}
```

Keep secrets in `.env` or user-level config, not in a checked-in `.mcp.json`.

## Codex

Codex reads MCP servers from `~/.codex/config.toml` or a trusted project `.codex/config.toml`.

Remote HTTP config:

```toml
[mcp_servers.orange]
url = "https://orange-api-production.up.railway.app/mcp/"
bearer_token_env_var = "ORANGE_MCP_TOKEN"
startup_timeout_sec = 20
tool_timeout_sec = 180
enabled = true
```

Then set the token locally before launching Codex:

```bash
export ORANGE_MCP_TOKEN=YOUR_ORANGE_MCP_TOKEN
codex
```

Local stdio config:

```toml
[mcp_servers.orange]
command = "/absolute/path/to/orange/venv311/bin/python"
args = ["-m", "core.mcp_server.server"]
cwd = "/absolute/path/to/orange"
startup_timeout_sec = 20
tool_timeout_sec = 180
enabled = true

[mcp_servers.orange.env]
PYTHONPATH = "/absolute/path/to/orange"
```

After launching Codex, check MCP status with `/mcp` if available, or ask Codex to call `orange_status`.

## Recommended Agent Behavior

At the start of a useful turn:

```json
{
  "query": "current user request or error",
  "user_email": "harsh@example.com",
  "source": "codex",
  "scope": "user"
}
```

Mid-session, when an important finding should not be lost:

```json
{
  "note": "Root cause: FastAPI middleware was registered after route setup.",
  "user_email": "harsh@example.com",
  "source": "codex"
}
```

At completion:

```json
{
  "source": "codex",
  "user_email": "harsh@example.com",
  "transcript": "full conversation transcript",
  "summary": "Fixed the recurring CORS preflight failure by moving middleware registration before route setup.",
  "key_entities": ["server.py", "CORSMiddleware"],
  "decisions": ["Keep middleware registration before routers."],
  "problems_solved": ["OPTIONS preflight returned 405."],
  "contribute_to_global": false
}
```

If remote bearer-token mapping is configured, `user_email` can be omitted.

Use `source: "claude"` for Claude Code, `source: "cursor"` for Cursor, and `source: "codex"` for Codex. If the client is unknown, use `source: "mcp"`.

## Seeing Nodes Get Created

1. Call `orange_status`.
2. Have a conversation with durable memory, for example: `Our company uses .md files as the memory source format. Remember this for future agents.`
3. At the end, call `complete_conversation` with `user_email`, or rely on bearer-token mapping.
4. Inspect:

```text
list_sessions(user_id="harsh@example.com")
inspect_graph(user_id="harsh@example.com")
chroma_peek(scope="user")
chroma_peek(scope="global")
```

If no nodes appear, check the `skipped_reason`. Generic tasks like `create a website` are skipped unless the user also provided reusable steering or facts.

## Troubleshooting

- `orange_status.neo4j.reachable=false`: check `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`.
- `orange_status.chroma.reachable=false`: check `CHROMA_PATH` and filesystem permissions.
- `complete_conversation` returns `skipped_reason`: triage decided the session had no durable user/company memory.
- Nodes do not show on Vercel: confirm the MCP server and Railway backend point to the same `NEO4J_URI`, and open the site with the same email.
- Claude/Codex cannot see tools: verify the configured Python path, `PYTHONPATH`, and run the MCP client's `/mcp` diagnostics.
