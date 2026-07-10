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
ORANGE_PUBLIC_BACKEND_URL=https://orange-api-x38s.onrender.com
```

Notes:

- `POSTGRES_DSN` is a server secret. On **Render Free (IPv4-only outbound)**,
  the Supabase **direct** host `db.<ref>.supabase.co` often resolves to
  **IPv6 only** and will fail health checks. Use the **session pooler** DSN
  (IPv4), for example:
  ```text
  postgresql://postgres.<project-ref>:<password>@aws-1-<region>.pooler.supabase.com:5432/postgres?sslmode=require
  ```
  Session mode (`:5432` on the pooler) is preferred for Orange's long-lived
  connection pool. Keep SSL enabled, and never expose the DSN through a
  `NEXT_PUBLIC_` variable.
- If you omit `ORANGE_PUBLIC_BACKEND_URL`, the app uses Render’s injected
  `RENDER_EXTERNAL_URL` for MCP OAuth `base_url`. Setting it explicitly is still
  recommended once you know the public hostname.
- Free web services **spin down after ~15 minutes idle**. The next request can
  take **30–60 seconds** to cold-start. Fine for small-scale demos; upgrade to a
  paid instance later if you need always-on MCP.

### Verify

```bash
curl https://orange-api-x38s.onrender.com/health
curl https://orange-api-x38s.onrender.com/health/deep
```

The deep health response should report Postgres and pgvector as healthy.

## 3. Vercel frontend

Set these values on the `site` project for Production, Preview, and Development:

```text
ORANGE_BACKEND_URL=https://orange-api-x38s.onrender.com
NEXT_PUBLIC_ORANGE_BACKEND_URL=https://orange-api-x38s.onrender.com
NEXT_PUBLIC_SUPABASE_URL=https://your-project-ref.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-browser-safe-publishable-key
```

`ORANGE_BACKEND_URL` is used by the Next.js API proxy.  
`NEXT_PUBLIC_ORANGE_BACKEND_URL` is used by the public MCP setup card on `/mcp`
(“Connect Orange” with short tabs for Grok, Claude, ChatGPT, and generic MCP).

Then deploy from `site/`:

```bash
vercel --prod
```

The site proxy forwards the signed-in user's short-lived Supabase access token
to Render. It does not forward a browser-supplied email as authorization.

## 4. MCP OAuth smoke test (provider-neutral)

Orange keeps **one** remote Streamable HTTP endpoint for every client:

```text
https://orange-api-x38s.onrender.com/mcp
```

There are no separate backends for Grok, Claude, or ChatGPT. Discovery, dynamic
client registration, PKCE, browser login, consent, token storage, and refresh
are the standard MCP OAuth path. Users never paste a bearer token or API key.

### Discovery (no auth)

```bash
curl -sS https://orange-api-x38s.onrender.com/.well-known/oauth-protected-resource/mcp
curl -sS https://orange-api-x38s.onrender.com/.well-known/oauth-authorization-server
# Unauthenticated MCP POST should be 401 with resource_metadata WWW-Authenticate.
```

### Grok first (test as `orange-remote` before replacing local stdio)

```bash
grok mcp add --scope user --transport http orange-remote \
  https://orange-api-x38s.onrender.com/mcp
```

Open Grok, run `/mcps`, select `orange-remote`, press `i`, complete browser
login. Then:

1. Call `orange_status`.
2. Store a non-trivial conversation via `complete_conversation`.
3. Poll `get_job_status` until it succeeds.
4. Confirm the new node appears in the deployed graph within one refresh cycle
   (scoped graph version poll).
5. Only then replace a working local `orange` stdio entry with the remote URL
   if desired.

```bash
python scripts/configure_mcp.py grok remote --name orange-remote
```

### Claude, then ChatGPT

Use the same URL with each client's MCP connector UI or CLI. Short instructions:

```bash
python scripts/configure_mcp.py claude
python scripts/configure_mcp.py chatgpt
python scripts/configure_mcp.py generic
```

Verify login + `orange_status` + a write tool in Grok first, then Claude, then
ChatGPT. Do not introduce provider-specific backend logic or hardcoded client
secrets.

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
