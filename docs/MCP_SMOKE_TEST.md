# Orange MCP smoke-test log

Provider-neutral endpoint:

```text
https://orange-api-x38s.onrender.com/mcp
```

Automated coverage (unit/integration mocks): OAuth protected-resource discovery,
401 `resource_metadata` challenges, AS metadata (DCR + PKCE S256), mocked
dynamic client registration + PKCE authorization-code token exchange, token
validation, user isolation, and MCP tool annotations/behavior.

This file records **manual** client smoke tests that require a human browser
login.

## Checklist (each client)

1. Add only the MCP URL (no bearer token / API key paste).
2. Complete browser OAuth (discovery → DCR → PKCE → consent).
3. Call `orange_status` (authenticated subject + Postgres healthy).
4. Call `complete_conversation` with a non-trivial note (`worth_storing=true`).
5. Poll `get_job_status` if queued; confirm a new node on the site graph.

## Recorded results

| Client | Date | Result | Notes |
|--------|------|--------|-------|
| Remote discovery (curl) | 2026-07-10 | **Pass** | `/.well-known/oauth-protected-resource/mcp` returns resource + Supabase AS; unauthenticated `POST /mcp` → `401` with `resource_metadata` |
| AS metadata (curl) | 2026-07-10 | **Pass** | Forwards `registration_endpoint` and `code_challenge_methods_supported: S256` |
| Grok `orange-remote` config | 2026-07-10 | **Pass (partial)** | Added HTTP server without replacing local stdio `orange`. `grok mcp doctor orange-remote` starts transport and correctly reports OAuth authorization required until browser login |
| Grok login + tools | 2026-07-10 | **Pending** | Interactive `/mcps` → `i` browser login not completed in this environment |
| Claude Code / Claude.ai | 2026-07-10 | **Pending** | Same URL; follow Connect Orange → Claude tab |
| ChatGPT Developer mode App | 2026-07-10 | **Pending** | Use Developer mode + developer-mode App (not Custom GPT Actions). Docs: https://developers.openai.com/api/docs/guides/developer-mode |

## How to update this table

After each manual pass, add a row (or update Pending → Pass/Fail) with date,
operator, and any cold-start or consent notes. Prefer testing **Grok first**,
then Claude, then ChatGPT.
