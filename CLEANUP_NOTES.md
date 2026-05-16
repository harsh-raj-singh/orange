# Cleanup Notes

| Area | Left Intentionally Untouched | Reason |
| --- | --- | --- |
| `core/graph_deduplication.py` | Oversized legacy graph-deduplication routines | Not on the active MCP/v2 writer path in tests, but could still be used by older Streamlit flows. Refactoring would be architectural. |
| `core/complete_chat_system.py` | Large `process_chat`, `_process_graph_concepts`, and retrieval methods | Still used by Streamlit/Slack legacy runtime paths. Cleanup removed dead vector code and broken runner calls only. |
| `core/graph_upsert/writer.py` | Oversized write helpers | High-risk persistence code covered by focused tests; no dead branches were obvious enough to remove safely. |
| `core/mcp_server/handlers.py` | Oversized MCP handler functions | Public MCP signatures and response shapes are externally depended on. |
| `site/package.json` | `@tailwindcss/postcss`, `tailwindcss`, `@types/node`, `@types/react-dom` | `depcheck` reports these as unused, but they are framework/config/type dependencies used by Next, Tailwind CSS, PostCSS, or Node-based scripts. |
| `site/package-lock.json` | `npm audit --omit=dev` reports a moderate PostCSS advisory through `next@16.2.6` | `npm audit fix --force` proposes a breaking downgrade to `next@9.3.3`; `npm view next version` reports `16.2.6` as latest, so this needs an upstream Next release rather than a local cleanup change. |
| `requirements.txt` | `sentence-transformers`, `uvicorn`, `dspy-ai` | Import usage is indirect or runtime-specific: Chroma's embedding function loads sentence transformers, `uvicorn` runs the FastAPI app, and DSPy imports as `dspy`. |
