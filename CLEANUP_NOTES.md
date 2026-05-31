# Cleanup Notes

Orange now has one active memory architecture:

```text
completed session -> triage -> scoped Insight extraction -> Neo4j + Chroma -> recall
```

The retired Streamlit/Mem0/DSPy and Problem/Solution writer stack has been removed from runtime code and tests. The remaining cleanup candidates are narrower:

| Area | Notes |
| --- | --- |
| `core/storage/supabase_store.py` | Still named after Supabase, but implemented as a direct Postgres metadata/audit store. |
| `core/graph_queries/neo4j_queries.py` | Generic graph reads remain for demo/MCP inspection; production admin auth should gate broad inspection routes. |
| `site/src/components/memory-graph.tsx` | Contains a local static visualization fallback for offline demo rendering. |
| `site/package-lock.json` | Keep Next dependency updates separate from this architecture cleanup. |
