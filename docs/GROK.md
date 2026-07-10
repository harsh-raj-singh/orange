# Orange with Grok CLI

Grok CLI connects to the same Orange Streamable HTTP MCP endpoint as Claude,
ChatGPT, and other clients:

```text
https://orange-api-x38s.onrender.com/mcp
```

Use the deployed server for normal testing so Grok and the Orange website read
and write the same Supabase Postgres memory store. There is no Grok-only MCP
backend.

## Recommended: deployed Orange with browser login

Add the hosted MCP URL once. No bearer token, API key, header, or environment
variable is required:

```bash
# Keep working local stdio as `orange` until remote login is verified:
grok mcp add --scope user --transport http orange-remote \
  https://orange-api-x38s.onrender.com/mcp
```

Then authenticate from Grok:

1. Launch `grok`.
2. Enter `/mcps`.
3. Select the `orange-remote` server and press `i`.
4. Complete the Orange email sign-in and consent flow in the browser window
   Grok opens.
5. Return to Grok. Call `orange_status`, then a small `complete_conversation`.

After remote works, promote it to the main name if you want:

```bash
grok mcp remove orange
grok mcp add --scope user --transport http orange \
  https://orange-api-x38s.onrender.com/mcp
```

Repository helpers:

```bash
python scripts/configure_mcp.py grok remote --name orange-remote
python scripts/configure_mcp.py grok remote
# historical alias:
python scripts/configure_grok_mcp.py remote
```

## Local stdio diagnostic mode

Local mode remains useful when developing or debugging the MCP process itself:

```bash
python scripts/configure_mcp.py grok local --email you@example.com
```

This starts `core.mcp_server.server` from the current checkout and uses the
storage and model-provider settings in the repository `.env`. It does not use
the browser OAuth flow because the process runs locally over stdio. Prefer the
remote setup when you need Grok writes to appear in the deployed website.

## Verify and test

After browser authentication:

```bash
grok mcp list
grok mcp doctor orange-remote
# or: grok mcp doctor orange
```

Useful prompts inside Grok:

```text
Call Orange orange_status and summarize the result.
```

```text
Use Orange complete_conversation to store this private test memory:
We decided that Grok should use Orange's remote MCP so the website and agent
share the same Supabase Postgres memory store. Mark it worth storing.
```

Open Orange with the same signed-in email, then view **My Memory**. The graph
checks for scoped changes every five seconds while it is visible and refreshes
when the stored graph version changes. Shared/company nodes additionally need
the same company identity in the MCP session and website.

## Troubleshooting

- If Grok shows that Orange needs authentication, open `/mcps`, select the
  server, and press `i` to restart the browser login.
- If the browser login opens but does not complete, confirm you returned through
  the Orange callback page and approved the requested MCP access.
- Run `grok mcp doctor orange --json` after authentication to separate
  configuration, transport, handshake, and tool-discovery failures.
- For local stdio failures, inspect `~/.grok/logs/mcp/orange.stderr.log`.
- If the server is healthy but no node is created, inspect the
  `complete_conversation` result. Triage may intentionally skip low-value text.
- If Grok stores a node but the website does not update, confirm Grok is using
  the deployed URL rather than local stdio and that both surfaces use the same
  user or company identity.
- If the deployed graph says `demo preview`, verify `ORANGE_BACKEND_URL` on
  Vercel and the Render health endpoint.
