# Deploying Orange Backend to Railway

The frontend is deployed separately on Vercel. Railway should deploy only the FastAPI backend from the repo root.

## Backend Entry Point

```bash
uvicorn core.viz_api.main:app --host 0.0.0.0 --port $PORT
```

Railway uses `/health` as a lightweight health check:

```json
{"status":"ok","service":"orange-backend"}
```

Use `/health/deep` when you want to verify Neo4j and Chroma connectivity after environment variables are set.

## Prerequisites

- Railway account at railway.com
- Railway CLI:

```bash
npm install -g @railway/cli
railway login
```

## First Deploy

```bash
railway init
railway up
railway domain
```

`railway domain` assigns a public URL, for example:

```text
https://orange-backend.up.railway.app
```

## Required Environment Variables

Set these in Railway before using the demo ingestion flow:

```bash
railway variables set NEO4J_URI=bolt://your-neo4j-host:7687
railway variables set NEO4J_USER=neo4j
railway variables set NEO4J_PASSWORD=your-password
railway variables set OPENAI_API_KEY=sk-...
railway variables set OPENAI_MODEL=gpt-5.4-nano
railway variables set ALLOWED_ORIGINS=https://site-sage-eta-18.vercel.app,http://localhost:3000,http://localhost:3004
```

The code also supports the existing Memgraph-style names:

```bash
railway variables set MEMGRAPH_URL=bolt://your-graph-host:7687
railway variables set MEMGRAPH_USERNAME=neo4j
railway variables set MEMGRAPH_PASSWORD=your-password
```

If Supabase/Postgres metadata persistence is enabled, set one of these:

```bash
railway variables set SUPABASE_DB_URL=postgresql://...
railway variables set POSTGRES_DSN=postgresql://...
railway variables set DATABASE_URL=postgresql://...
```

Optional alternative LLM provider variables:

```bash
railway variables set NVIDIA_API_KEY=...
railway variables set NVIDIA_MODEL=...
railway variables set OPENAI_BASE_URL=...
railway variables set NVIDIA_BASE_URL=...
```

## Chroma Persistence

Orange currently uses `chromadb.PersistentClient`. Railway filesystems are ephemeral unless a volume is mounted, so this is the most important production setup detail.

Use a Railway Volume mounted at:

```text
/data/chroma
```

Then set:

```bash
railway variables set CHROMA_PATH=/data/chroma
```

Without this volume, Chroma vectors can disappear on redeploy even though Neo4j nodes remain.

## Neo4j Hosting

Recommended: use Neo4j AuraDB Free at neo4j.com/aura. It is managed, reachable from Railway, and gives you a Bolt URI quickly.

Set the Aura values in Railway:

```bash
railway variables set NEO4J_URI=neo4j+s://your-aura-host.databases.neo4j.io
railway variables set NEO4J_USER=neo4j
railway variables set NEO4J_PASSWORD=your-aura-password
```

Alternative: self-host Neo4j as a second Railway service, then point `NEO4J_URI` at that service.

## Wire Railway to Vercel

After Railway gives you the public backend URL, go to:

```text
Vercel dashboard -> orange/site project -> Settings -> Environment Variables
```

Add:

```text
ORANGE_BACKEND_URL=https://your-railway-url.up.railway.app
```

Then redeploy the frontend:

```bash
vercel --prod
```

You can also trigger a redeploy from the Vercel dashboard.

## Verify End to End

1. Check the backend:

```bash
curl https://your-railway-url.up.railway.app/health
```

Expected:

```json
{"status":"ok","service":"orange-backend"}
```

2. Check backing services:

```bash
curl https://your-railway-url.up.railway.app/health/deep
```

Expected after Neo4j and Chroma are configured:

```json
{"neo4j":"ok","chroma":"ok","status":"healthy"}
```

3. Open the frontend:

```text
https://site-sage-eta-18.vercel.app
```

4. Complete a demo chat and mark it done.

5. Refresh the page. Graph nodes should persist because the frontend is reading from Railway -> Neo4j/Chroma, not fallback memory.

6. Check Vercel function logs. You should no longer see fallback warnings from the graph route.
