# Deploying Orange

Orange uses three managed pieces:

- **Supabase Free**: Postgres graph, pgvector embeddings, durable jobs, Auth/OAuth, and Realtime change rows.
- **Render Free**: FastAPI + remote MCP resource server + in-process memory worker.
- **Vercel**: Next.js UI, Supabase login/consent, and authenticated API proxy.

Neo4j, Memgraph, Chroma, and a host data volume are not required.

> **Migration note (Railway → Render):** Railway trial credit is no longer required.
> The backend image is the same (`Dockerfile.railway`). Only the host URL and
> platform env vars change.

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

## 2. Render backend (replaces Railway)

### Option A — Blueprint (recommended)

1. Push this repo (includes `render.yaml`) to GitHub:
   `https://github.com/harsh-raj-singh/orange`
2. Open [Render → New → Blueprint](https://dashboard.render.com/select-repo?type=blueprint).
3. Connect the `harsh-raj-singh/orange` repo.
4. Select the branch that contains this deploy config
   (currently `codex/memory-graph-cache` until merged to `main`).
5. Render creates the `orange-api` free web service from `Dockerfile.railway`.
6. When prompted, fill secrets marked `sync: false` in `render.yaml` (below).

### Option B — Manual web service

1. **New → Web Service** → connect `harsh-raj-singh/orange`.
2. Runtime: **Docker**, Dockerfile path: `Dockerfile.railway`.
3. Instance type: **Free**.
4. Health check path: `/health`.
5. Optional start override:
   ```bash
   uvicorn core.viz_api.main:app --host 0.0.0.0 --port $PORT
   ```

### Environment variables

Set these at the **service** level (not as `NEXT_PUBLIC_*`):

```text
POSTGRES_DSN=postgresql://...?...sslmode=require
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_JWT_ALGORITHM=ES256
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.4-nano
ORANGE_MEMORY_WRITE_MODE=queued
ALLOWED_ORIGINS=https://your-site.vercel.app,http://localhost:3000,http://localhost:3004
ORANGE_PUBLIC_BACKEND_URL=https://orange-api-xxxx.onrender.com
```

Notes:

- `POSTGRES_DSN` is a server secret. Prefer the Supabase **direct** or
  **session pooler** URL for this long-running process, keep SSL enabled, and
  never expose it through a `NEXT_PUBLIC_` variable.
- If you omit `ORANGE_PUBLIC_BACKEND_URL`, the app uses Render’s injected
  `RENDER_EXTERNAL_URL` for MCP OAuth `base_url`. Setting it explicitly is still
  recommended once you know the public hostname.
- Free web services **spin down after ~15 minutes idle**. The next request can
  take **30–60 seconds** to cold-start. Fine for small-scale demos; upgrade to a
  paid instance later if you need always-on MCP.

### Verify

```bash
curl https://orange-api-xxxx.onrender.com/health
curl https://orange-api-xxxx.onrender.com/health/deep
```

The deep health response should report Postgres and pgvector as healthy.

## 3. Vercel frontend

Set these values on the `site` project for Production, Preview, and Development:

```text
ORANGE_BACKEND_URL=https://orange-api-xxxx.onrender.com
NEXT_PUBLIC_ORANGE_BACKEND_URL=https://orange-api-xxxx.onrender.com
NEXT_PUBLIC_SUPABASE_URL=https://your-project-ref.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-browser-safe-publishable-key
```

`ORANGE_BACKEND_URL` is used by the Next.js API proxy.  
`NEXT_PUBLIC_ORANGE_BACKEND_URL` is used by the public MCP setup card on `/mcp`.

Then deploy from `site/`:

```bash
vercel --prod
```

The site proxy forwards the signed-in user's short-lived Supabase access token
to Render. It does not forward a browser-supplied email as authorization.

## 4. Grok CLI OAuth test

Add only Orange's MCP URL:

```bash
grok mcp remove orange
grok mcp add --scope user --transport http orange \
  https://orange-api-xxxx.onrender.com/mcp
```

Open Grok, run `/mcps`, select Orange, and press `i`. Grok performs discovery,
dynamic client registration, PKCE, browser login, consent, token storage, and
refresh. No bearer header or copied Supabase key is part of the user flow.

After signing in:

1. Call `orange_status`.
2. Store a non-trivial conversation.
3. Poll `get_job_status` until it succeeds.
4. Confirm the new node appears in the deployed graph within one refresh cycle.
5. Restart the Render service (or wait for a cold start) and confirm Grok
   reconnects without another token paste.

## Optional Slack worker

Set `ENABLE_SLACK_BOT=true` plus the Slack app secrets if the API service should
also run the Socket Mode recorder. On Render free tier, prefer leaving Slack
disabled or running it as a separate always-on process later — Socket Mode does
not survive free-tier spin-down well.

## Free-tier caveats

| Concern | Behavior on Render Free |
|--------|-------------------------|
| Idle | Spins down after ~15 minutes without traffic |
| Cold start | ~30–60s on next request |
| Hours | ~750 free instance hours/month (enough for one always-warm service if it never slept; free tier still sleeps) |
| Database | Use Supabase Free — do **not** attach Render free Postgres for Orange |

## Railway (legacy)

`railway.toml` and `Dockerfile.railway` remain so an old Railway project can
still build the same image if you later enable a paid Railway plan. New
deployments should use Render.
