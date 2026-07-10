from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

import os
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from core.auth import get_mcp_identity, get_supabase_auth_provider
from core.mcp_server.handlers import handle_recall_memory, handle_store_session
from core.mcp_server.models import (
    RecallMemoryRequest,
    StoreSessionRequest,
)
try:
    from fastmcp import FastMCP
except Exception as exc:  # noqa: BLE001
    raise RuntimeError("fastmcp is required: pip install fastmcp") from exc


_AUTH_PROVIDER = get_supabase_auth_provider()
_APP = FastMCP("orange", auth=_AUTH_PROVIDER)
_LLM_CLIENT: Any | None = None
_POSTGRES_STORE: Any | None = None

ORANGE_INSTRUCTIONS = """## Orange Memory Protocol

### START of every session
Call recall_memory with a short query describing the current task before 
doing any work. This hydrates context from prior sessions.

### DURING a session
Call checkpoint_context whenever:
- A non-obvious solution is found
- An important architectural decision is made
- A root cause is identified
Do NOT call complete_conversation mid-session.

### END of session (final answer given, or user says done/remember/store/wrap)
Call complete_conversation with transcript or messages.
- Provide summary, key_entities, decisions, problems_solved if possible.
- Set worth_storing=false for trivial sessions (greetings, generic Q&A, 
  one-off lookups with no durable content).
- Leave worth_storing unset to let Orange triage decide automatically.
- This must be the LAST tool call before ending the response.

### Identity
Always pass user_email when available. For org/company memory, pass company 
or org_id. If using a remote MCP token, user_email is inferred automatically."""

COMPLETION_POLICY = ORANGE_INSTRUCTIONS

RECALL_MEMORY_DESCRIPTION = (
    "Call this BEFORE starting any coding or problem-solving work. Pass the current user request as `query`. "
    "Retrieves relevant memory through scoped Supabase pgvector search and Postgres graph hydration. "
    "Returns matched_nodes and neighborhood. Use user_email for personal memory, company or org_id for shared org memory."
)

COMPLETE_CONVERSATION_DESCRIPTION = (
    "Call this ONCE at the end of a useful work session, or when the user says done/remember/store/wrap. "
    "Provide the full transcript or messages list. Optionally add a summary, key_entities, decisions, and "
    "problems_solved for higher-quality storage. Set worth_storing=false for trivial or unproductive sessions "
    "to skip triage entirely. Set worth_storing=true only if you are certain the session has durable memory value. "
    "Leave worth_storing unset to let Orange triage decide. Do NOT call this mid-session."
)

CHECKPOINT_CONTEXT_DESCRIPTION = (
    "Call this mid-session to save an important decision, finding, or non-obvious solution before it can be lost. "
    "Writes a lightweight durable Postgres/pgvector checkpoint. Use when something important just happened that you "
    "don't want to lose if the session ends unexpectedly. Safe to call multiple times per session."
)

TOOL_LIST = [
    "orange_status",
    "recall_memory",
    "checkpoint_context",
    "complete_conversation",
    "store_session",
    "inspect_graph",
    "get_node",
    "get_session_graph",
    "list_sessions",
    "get_job_status",
    "memory_peek",
]


class OpenAILLMAdapter:
    """Sync adapter exposing generate_response(messages=[...]) for arbitration calls."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        from openai import OpenAI

        if base_url:
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = OpenAI(api_key=api_key)
        self._model = model

    def generate_response(self, messages: list[dict[str, str]]) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.0,
            max_tokens=300,
        )
        if not response.choices:
            return "{}"
        content = response.choices[0].message.content
        return content if isinstance(content, str) else "{}"


def get_postgres_store() -> Any:
    global _POSTGRES_STORE
    if _POSTGRES_STORE is not None:
        return _POSTGRES_STORE
    from core.viz_api.dependencies import get_memory_repository

    _POSTGRES_STORE = get_memory_repository()
    return _POSTGRES_STORE


def get_llm() -> Any:
    global _LLM_CLIENT
    if _LLM_CLIENT is not None:
        return _LLM_CLIENT

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("NVIDIA_API_KEY")
    if not api_key:
        _LLM_CLIENT = None
        return _LLM_CLIENT

    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("NVIDIA_BASE_URL")
    model = os.getenv("OPENAI_MODEL") or os.getenv("NVIDIA_MODEL") or "gpt-5.4-nano"
    _LLM_CLIENT = OpenAILLMAdapter(api_key=api_key, model=model, base_url=base_url)
    return _LLM_CLIENT


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


class MissingOAuthConfigurationMiddleware:
    """Fail closed when somebody starts remote MCP without Supabase Auth."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or _truthy_env("ORANGE_MCP_ALLOW_UNAUTHENTICATED"):
            await self.app(scope, receive, send)
            return
        from starlette.responses import JSONResponse

        await JSONResponse(
            {"error": "SUPABASE_URL is required for browser-authenticated remote MCP."},
            status_code=503,
        )(scope, receive, send)


def _http_middleware() -> list[Any]:
    if _AUTH_PROVIDER is not None:
        return []
    from starlette.middleware import Middleware

    return [Middleware(MissingOAuthConfigurationMiddleware)]


def create_http_app(path: str = "/mcp"):
    """Create the ASGI app used when Orange MCP is mounted on FastAPI."""

    return _APP.http_app(path=path, middleware=_http_middleware(), stateless_http=True)


def _default_user_email(value: str | None) -> str | None:
    identity = get_mcp_identity()
    if identity and identity.email:
        return identity.email
    cleaned = (value or "").strip().lower()
    if cleaned:
        return cleaned
    env_email = (os.getenv("ORANGE_USER_EMAIL") or "").strip().lower()
    return env_email or None


def _default_user_id(value: str | None, email: str | None = None) -> str:
    identity = get_mcp_identity()
    if identity:
        return identity.subject
    return (value or email or os.getenv("ORANGE_USER_ID") or "").strip()


def _auth_metadata() -> dict[str, str]:
    identity = get_mcp_identity()
    return {"auth_user_id": identity.subject} if identity else {}


def _check_postgres() -> dict[str, Any]:
    status: dict[str, Any] = {
        "reachable": False,
        "pgvector_version": None,
        "session_count": None,
        "insight_count": None,
        "queued_jobs": None,
        "dead_letter_jobs": None,
    }
    try:
        repository = get_postgres_store()
        with repository.pool.connection() as conn:
            row = conn.execute(
                """
                select
                  (select extversion from pg_extension where extname = 'vector') as pgvector_version,
                  (select count(*) from orange.memory_sessions) as session_count,
                  (select count(*) from orange.insights) as insight_count,
                  (select count(*) from orange.memory_write_jobs where status in ('queued', 'retrying')) as queued_jobs,
                  (select count(*) from orange.memory_write_jobs where status = 'dead_letter') as dead_letter_jobs
                """
            ).fetchone()
        status.update(
            {
                "reachable": True,
                "pgvector_version": row.get("pgvector_version"),
                "session_count": int(row.get("session_count") or 0),
                "insight_count": int(row.get("insight_count") or 0),
                "queued_jobs": int(row.get("queued_jobs") or 0),
                "dead_letter_jobs": int(row.get("dead_letter_jobs") or 0),
            }
        )
    except Exception:  # noqa: BLE001
        pass
    return status


def _auth_status() -> dict[str, Any]:
    identity = get_mcp_identity()
    expires_at: str | None = None
    if identity:
        try:
            exp = int(identity.claims.get("exp") or 0)
            if exp:
                expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            expires_at = None
    return {
        "provider": "supabase_oauth",
        "configured": _AUTH_PROVIDER is not None,
        "authenticated": identity is not None,
        "subject": identity.subject if identity else None,
        "user_email": identity.email if identity else None,
        "token_expires_at": expires_at,
    }


def _mode() -> str:
    transport = (os.getenv("ORANGE_MCP_TRANSPORT") or "stdio").strip().lower()
    if get_mcp_identity() or transport in {"http", "streamable-http", "sse"}:
        return "remote"
    return "local"


def _queued_writes() -> bool:
    return os.getenv("ORANGE_MEMORY_WRITE_MODE", "inline").strip().lower() == "queued"


def _status_warnings(
    *,
    postgres_status: dict[str, Any],
    auth_status: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if not postgres_status.get("reachable"):
        warnings.append("Supabase Postgres is unreachable; memory reads, writes, and jobs will fail.")
    if postgres_status.get("reachable") and not postgres_status.get("pgvector_version"):
        warnings.append("The pgvector extension is missing from Supabase Postgres.")
    if int(postgres_status.get("dead_letter_jobs") or 0) > 0:
        warnings.append("One or more extraction jobs need dead-letter review.")
    if not auth_status.get("configured"):
        warnings.append("Supabase OAuth is not configured for remote MCP.")
    return warnings


@_APP.tool()
async def orange_status() -> dict:
    """Return structured Orange MCP health, auth, schema, and tool information."""

    postgres_status = await asyncio.to_thread(_check_postgres)
    auth_status = _auth_status()
    return {
        "storage": "supabase-postgres-pgvector",
        "postgres": postgres_status,
        "auth": auth_status,
        "mode": _mode(),
        "warnings": _status_warnings(
            postgres_status=postgres_status,
            auth_status=auth_status,
        ),
        "tool_list": TOOL_LIST,
    }


@_APP.tool(description=RECALL_MEMORY_DESCRIPTION)
async def recall_memory(
    query: str,
    user_id: str = "",
    source: str = "mcp",
    scope: str = "user",
    user_email: str | None = None,
    org_id: str | None = None,
    company: str | None = None,
    min_score: float = 0.70,
) -> dict:
    """Retrieve relevant Orange memory before coding or problem-solving work."""

    resolved_email = _default_user_email(user_email)
    identity = _default_user_id(user_id, resolved_email)
    req = RecallMemoryRequest(
        query=query,
        user_id=identity,
        source=source,
        scope=scope,
        user_email=resolved_email,
        org_id=org_id,
        company=company,
        min_score=min_score,
    )
    resp = await handle_recall_memory(req, repository=get_postgres_store())
    return asdict(resp)


@_APP.tool(description=COMPLETE_CONVERSATION_DESCRIPTION)
async def complete_conversation(
    transcript: str = "",
    source: str = "mcp",
    user_email: str | None = None,
    company: str | None = None,
    user_id: str = "",
    session_id: str = "",
    org_id: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    client_name: str | None = None,
    client_version: str | None = None,
    source_url: str | None = None,
    metadata: dict[str, Any] | None = None,
    contribute_to_global: bool = False,
    summary: str = "",
    key_entities: list[str] = [],
    decisions: list[str] = [],
    problems_solved: list[str] = [],
    worth_storing: bool | None = None,
    scope: str | None = None,
    session_duration_turns: int = 0,
) -> dict:
    """Mark a conversation as complete and write durable Orange memory.

    This is the preferred write tool for Claude Code, Codex, Cursor, and other MCP clients.
    Call it once at the end of a useful session using the full transcript or message list.
    Orange triage may still skip storage if the conversation contains no durable memory.
    """

    if worth_storing is False:
        return {"stored": False, "reason": "caller marked not worth storing"}

    resolved_email = _default_user_email(user_email)
    identity = _default_user_id(user_id, resolved_email)
    req = StoreSessionRequest(
        transcript=transcript,
        source=source,
        user_id=identity,
        user_email=resolved_email,
        session_id=session_id,
        org_id=org_id,
        company=company,
        ended_at=datetime.now(timezone.utc).isoformat(),
        messages=messages or [],
        client_name=client_name,
        client_version=client_version,
        source_url=source_url,
        metadata={
            **(metadata or {}),
            **_auth_metadata(),
            "completion_policy": "agent_final_answer_or_user_done_signal",
            "completed_via": "complete_conversation",
        },
        contribute_to_global=contribute_to_global,
        summary=summary,
        key_entities=key_entities or [],
        decisions=decisions or [],
        problems_solved=problems_solved or [],
        worth_storing=worth_storing,
        scope=scope,
        session_duration_turns=session_duration_turns,
    )
    resp = await handle_store_session(
        req,
        repository=get_postgres_store(),
        llm=get_llm(),
        enqueue_only=_queued_writes(),
    )
    payload = asdict(resp)
    payload["completion_policy"] = COMPLETION_POLICY
    payload["stored"] = (
        payload.get("job_status") == "succeeded"
        or (bool(payload.get("insights_stored")) and not payload.get("errors"))
    )
    return payload


@_APP.tool(description=CHECKPOINT_CONTEXT_DESCRIPTION)
async def checkpoint_context(
    note: str,
    user_email: str | None = None,
    user_id: str = "",
    org_id: str | None = None,
    company: str | None = None,
    source: str = "mcp",
) -> dict:
    """Write a lightweight mid-session checkpoint to Postgres + pgvector."""

    cleaned_note = (note or "").strip()
    if not cleaned_note:
        raise ValueError("note is required")
    resolved_email = _default_user_email(user_email)
    auth_identity = get_mcp_identity()
    return await asyncio.to_thread(
        get_postgres_store().checkpoint_context,
        cleaned_note,
        user_email=resolved_email,
        user_id=_default_user_id(user_id, resolved_email),
        auth_user_id=auth_identity.subject if auth_identity else None,
        org_id=org_id,
        company=company,
        source=source,
        scope="user",
    )


@_APP.resource("orange://instructions", name="orange_instructions", mime_type="text/markdown")
def orange_instructions() -> str:
    """Readable Orange Memory Protocol instructions for MCP clients."""

    return ORANGE_INSTRUCTIONS


@_APP.tool()
async def store_session(
    transcript: str,
    source: str,
    user_id: str = "",
    user_email: str | None = None,
    session_id: str = "",
    org_id: str | None = None,
    company: str | None = None,
    external_session_id: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    participants: list[dict[str, Any]] | None = None,
    client_name: str | None = None,
    client_version: str | None = None,
    source_url: str | None = None,
    client_metadata: dict[str, Any] | None = None,
    tool_metadata: dict[str, Any] | None = None,
    messages: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    contribute_to_global: bool = True,
    scope: str | None = None,
) -> dict:
    """Low-level ingestion tool. Prefer complete_conversation for agent/client integrations."""

    resolved_email = _default_user_email(user_email)
    req = StoreSessionRequest(
        transcript=transcript,
        source=source,
        user_id=_default_user_id(user_id, resolved_email),
        user_email=resolved_email,
        session_id=session_id,
        external_session_id=external_session_id,
        org_id=org_id,
        company=company,
        started_at=started_at,
        ended_at=ended_at,
        participants=participants or [],
        client_name=client_name,
        client_version=client_version,
        source_url=source_url,
        client_metadata=client_metadata or {},
        tool_metadata=tool_metadata or {},
        messages=messages or [],
        metadata={**(metadata or {}), **_auth_metadata()},
        contribute_to_global=contribute_to_global,
        scope=scope,
    )
    resp = await handle_store_session(
        req,
        repository=get_postgres_store(),
        llm=get_llm(),
        enqueue_only=_queued_writes(),
    )
    return asdict(resp)


@_APP.tool()
async def inspect_graph(
    user_id: str = "",
    user_email: str | None = None,
    org_id: str | None = None,
    company: str | None = None,
    scope: str = "user",
    limit: int = 500,
    offset: int = 0,
) -> dict:
    """Inspect a page of the authenticated user's Postgres memory graph."""

    email = _default_user_email(user_email)
    return await asyncio.to_thread(
        get_postgres_store().get_full_graph,
        user_id=_default_user_id(user_id, email),
        user_email=email,
        org_id=org_id or company,
        scope=scope,
        limit=limit,
        offset=offset,
    )


@_APP.tool()
async def get_node(
    node_id: str,
    user_id: str = "",
    user_email: str | None = None,
    org_id: str | None = None,
    company: str | None = None,
    scope: str = "user",
) -> dict:
    """Return one graph node with its immediate neighborhood."""

    email = _default_user_email(user_email)
    return await asyncio.to_thread(
        get_postgres_store().get_node_with_neighborhood,
        node_id,
        user_id=_default_user_id(user_id, email),
        user_email=email,
        org_id=org_id or company,
        scope=scope,
    )


@_APP.tool()
async def get_session_graph(
    session_id: str,
    user_id: str = "",
    user_email: str | None = None,
    org_id: str | None = None,
    company: str | None = None,
    scope: str = "user",
) -> dict:
    """Return the subgraph produced by one stored session."""

    email = _default_user_email(user_email)
    return await asyncio.to_thread(
        get_postgres_store().get_session_subgraph,
        session_id,
        user_id=_default_user_id(user_id, email),
        user_email=email,
        org_id=org_id or company,
        scope=scope,
    )


@_APP.tool()
async def list_sessions(
    user_id: str = "",
    user_email: str | None = None,
    org_id: str | None = None,
    company: str | None = None,
    scope: str = "user",
    limit: int = 100,
    offset: int = 0,
) -> list:
    """List stored Orange sessions, optionally filtered by user_id/email."""

    email = _default_user_email(user_email)
    return await asyncio.to_thread(
        get_postgres_store().list_sessions,
        user_id=_default_user_id(user_id, email),
        user_email=email,
        org_id=org_id or company,
        scope=scope,
        limit=limit,
        offset=offset,
    )


@_APP.tool()
async def get_job_status(job_id: str, user_email: str | None = None) -> dict:
    """Return durable extraction progress/result for a completed-session job."""

    job = await asyncio.to_thread(
        get_postgres_store().get_memory_write_job,
        job_id=job_id,
    )
    if not job:
        raise ValueError("Memory job was not found.")
    verified_email = _default_user_email(user_email)
    job_email = str(job.get("user_email") or "").strip().lower()
    if verified_email and job_email and verified_email != job_email:
        raise PermissionError("This memory job belongs to a different user.")
    return {
        key: job.get(key)
        for key in (
            "id",
            "status",
            "attempt_count",
            "max_attempts",
            "available_at",
            "last_attempt_at",
            "completed_at",
            "dead_lettered_at",
            "error",
            "result",
            "session_id",
            "source",
        )
    }


@_APP.tool()
async def memory_peek(
    limit: int = 10,
    scope: str = "user",
    user_id: str = "",
    user_email: str | None = None,
    org_id: str | None = None,
    company: str | None = None,
) -> dict:
    """Inspect recent graph-safe memory rows without exposing embeddings."""

    graph = await inspect_graph(
        user_id=user_id,
        user_email=user_email,
        org_id=org_id,
        company=company,
        scope=scope,
        limit=max(limit * 2, limit),
    )
    insights = [node for node in graph.get("nodes", []) if node.get("label") == "Insight"][:limit]
    return {"count": len(insights), "scope": scope, "nodes": insights}


if __name__ == "__main__":
    transport = (os.getenv("ORANGE_MCP_TRANSPORT") or "stdio").strip().lower()
    if transport in {"http", "streamable-http", "sse"}:
        _APP.run(
            transport=transport,
            host=os.getenv("ORANGE_MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("ORANGE_MCP_PORT") or os.getenv("PORT") or "8000"),
            path=os.getenv("ORANGE_MCP_PATH", "/mcp"),
            middleware=_http_middleware(),
            stateless_http=True,
        )
    else:
        _APP.run()
