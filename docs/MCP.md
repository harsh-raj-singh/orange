# Orange MCP Setup

Orange exposes a local stdio MCP server for coding agents. The intended loop is:

```text
agent starts work
  -> ping_context(query, user_email, company)
  -> use returned memory while answering
agent reaches final answer / user says done
  -> complete_conversation(transcript or messages, user_email, company)
  -> Orange triages and writes Insight nodes
```

The write path is session-level. Nothing is extracted mid-session. The agent calls `complete_conversation` once when the session is meaningfully done.

## Conversation Completion Rule

For now, a conversation is complete when either:

- the agent is about to send its final answer for a useful work session
- the user says `done`, `remember this`, `store this`, `mark complete`, or `wrap this`

Do not call completion for trivial greetings or generic one-off answers unless the user stated durable facts, preferences, company workflow details, or steering that future agents should remember.

Orange still runs triage after completion. If the session has no durable memory, `complete_conversation` returns `skipped_reason` and writes no nodes.

## Tools

- `orange_status`: verifies Neo4j, Chroma, env configuration, and returns the completion policy.
- `ping_context`: retrieves private user memory and company-scoped shared memory before answering.
- `complete_conversation`: preferred write tool for Claude Code, Codex, Cursor, and other MCP clients.
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
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
CHROMA_PATH=./chroma_db
```

Company/shared memory only works when the MCP client passes `company` or `org_id`. Company graphs are isolated by normalized `org_id`.

## Run Locally

```bash
PYTHONPATH=. python -m core.mcp_server.server
```

The process speaks MCP over stdio, so it will wait for an MCP client to connect.

## Claude Code

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
  "company": "Orange",
  "source": "codex",
  "scope": "both"
}
```

At completion:

```json
{
  "source": "codex",
  "user_email": "harsh@example.com",
  "company": "Orange",
  "transcript": "full conversation transcript",
  "contribute_to_global": true
}
```

Use `source: "claude"` for Claude Code, `source: "cursor"` for Cursor, and `source: "codex"` for Codex. If the client is unknown, use `source: "mcp"`.

## Seeing Nodes Get Created

1. Call `orange_status`.
2. Have a conversation with durable memory, for example: `Our company uses .md files as the memory source format. Remember this for future agents.`
3. At the end, call `complete_conversation` with `user_email` and `company`.
4. Inspect:

```text
list_sessions(user_id="harsh@example.com")
inspect_graph(user_id="harsh@example.com")
chroma_peek(scope="user")
chroma_peek(scope="global")
```

If no nodes appear, check the `skipped_reason`. Generic tasks like `create a website` are skipped unless the user also provided reusable steering or facts.

## Troubleshooting

- `orange_status.neo4j.ok=false`: check `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`.
- `orange_status.chroma.ok=false`: check `CHROMA_PATH` and filesystem permissions.
- `complete_conversation` returns `skipped_reason`: triage decided the session had no durable user/company memory.
- Company memory missing: pass `company` or `org_id`; global/company retrieval is intentionally scoped by company.
- Claude/Codex cannot see tools: verify the configured Python path, `PYTHONPATH`, and run the MCP client's `/mcp` diagnostics.
