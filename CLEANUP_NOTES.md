# Cleanup Notes

Orange has one production memory architecture:

```text
completed session
-> durable Postgres job
-> triage + scoped Insight extraction
-> transactional Session/Insight/edge + pgvector write
-> scoped recall and live graph-version refresh
```

Neo4j, Memgraph, Chroma, copied MCP bearer tokens, and their deployment scripts
have been removed from the production path and dependencies.

The old fake Neo4j/Chroma writer/query modules remain temporarily as isolated
test compatibility fixtures for historical regression coverage. No API, MCP,
Slack, worker, or UI code imports them at runtime. They can be deleted together
when those legacy regression tests are converted to repository-level fixtures.

The static frontend graph is intentionally retained as a signed-out/offline
product preview. Authenticated users never fall back from one identity to
another user's live data; the last successful authorized snapshot is retained
during a transient backend outage.
