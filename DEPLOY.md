# Deploying Orange

Orange uses three managed pieces:

- Supabase Free: Postgres graph, pgvector embeddings, durable jobs, Auth/OAuth, and Realtime change rows.
- Railway: FastAPI + remote MCP resource server + memory worker.
- Vercel: Next.js UI, Supabase login/consent, and authenticated API proxy.

Neo4j, Memgraph, Chroma, and a Railway data volume are not required.

## 1. Supabase

Link the intended project and apply every migration:

```bash
supabase link --project-ref your-project-ref
supabase db push --linked --dry-run
supabase db push --linked
```

The migrations create the private `orange` schema, the 1536-dimensional
pgvector columns/indexes, scoped graph tables, RLS policies, leased jobs, graph
version triggers, and Realtime publication entries.

In Supabase Authentication:

1. Use an asymmetric ES256 signing key.
2. Set the site URL to the deployed Vercel origin.
3. Allow the Vercel and local callback URLs.
4. Enable OAuth Server and dynamic OAuth application registration.
5. Set the authorization path to `/oauth/consent`.

The OAuth discovery endpoint should respond successfully:

```text
https://your-project-ref.supabase.co/.well-known/oauth-authorization-server/auth/v1
```

## 2. Railway backend

Railway uses `Dockerfile.railway` and this start command:

```bash
uvicorn core.viz_api.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Set these variables once at the deployment level; end users never see or copy
them:

```text
POSTGRES_DSN=postgresql://...?...sslmode=require
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_JWT_ALGORITHM=ES256
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.4-nano
ORANGE_PUBLIC_BACKEND_URL=https://your-backend.up.railway.app
ORANGE_MEMORY_WRITE_MODE=queued
ALLOWED_ORIGINS=https://your-site.vercel.app,http://localhost:3000,http://localhost:3004
```

`POSTGRES_DSN` is a server secret. Prefer the Supabase direct/session-pooler URL
for this long-running process, keep SSL enabled, and never expose it through a
`NEXT_PUBLIC_` variable.

Deploy and verify:

```bash
railway up
curl https://your-backend.up.railway.app/health
curl https://your-backend.up.railway.app/health/deep
```

The deep health response should report Postgres and pgvector as healthy.

## 3. Vercel frontend

Set these values on the `site` project for Production, Preview, and Development:

```text
ORANGE_BACKEND_URL=https://your-backend.up.railway.app
NEXT_PUBLIC_SUPABASE_URL=https://your-project-ref.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-browser-safe-publishable-key
```

Then deploy from `site/`:

```bash
vercel --prod
```

The site proxy forwards the signed-in user's short-lived Supabase access token
to Railway. It does not forward a browser-supplied email as authorization.

## 4. Grok CLI OAuth test

Add only Orange's MCP URL:

```bash
grok mcp remove orange
grok mcp add --scope user --transport http orange \
  https://your-backend.up.railway.app/mcp
```

Open Grok, run `/mcps`, select Orange, and press `i`. Grok performs discovery,
dynamic client registration, PKCE, browser login, consent, token storage, and
refresh. No bearer header or copied Supabase key is part of the user flow.

After signing in:

1. Call `orange_status`.
2. Store a non-trivial conversation.
3. Poll `get_job_status` until it succeeds.
4. Confirm the new node appears in the deployed graph within one refresh cycle.
5. Restart Railway and confirm Grok reconnects without another token paste.

## Optional Slack worker

Set `ENABLE_SLACK_BOT=true` plus the Slack app secrets if the API service should
also run the Socket Mode recorder. It uses the same Supabase Postgres store and
worker path as MCP and the website.
