# Orange memory protocol

When the `orange` MCP server is available:

- Before substantial coding or debugging work, discover and call `orange__recall_memory` with a short description of the current task.
- Call `orange__checkpoint_context` after a non-obvious root cause or architectural decision is found.
- At the end of a useful session, call `orange__complete_conversation` once with a concise transcript or structured summary, decisions, and problems solved.
- Set `worth_storing=false` for greetings, generic questions, and other trivial sessions.
- Use private/user scope unless a company is explicitly known and the information is appropriate for coworkers.
- Never invent an email or company. With remote Orange, the bearer token supplies the private email identity.
