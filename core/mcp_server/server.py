from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from core.graph_queries.neo4j_queries import (
    get_all_sessions,
    get_full_graph,
    get_node_with_neighborhood,
    get_session_subgraph,
)
from core.graph_upsert.dedup import (
    ORANGE_GLOBAL_VECTOR_COLLECTION,
    ORANGE_USER_VECTOR_COLLECTION,
    get_or_create_global_collection,
    get_or_create_user_collection,
)
from core.mcp_server.handlers import handle_ping_context, handle_resolve_problem, handle_store_session
from core.mcp_server.models import (
    PingContextRequest,
    ResolveProblemRequest,
    StoreSessionRequest,
)

try:
    from fastmcp import FastMCP
except Exception as exc:  # noqa: BLE001
    raise RuntimeError("fastmcp is required: pip install fastmcp") from exc


_APP = FastMCP("orange")
_NEO4J_CLIENT: Any | None = None
_CHROMA_CLIENT: Any | None = None
_LLM_CLIENT: Any | None = None
_POSTGRES_STORE: Any | None = None
_POSTGRES_DISABLED = False

COMPLETION_POLICY = (
    "Call complete_conversation exactly once when the agent is about to give the final answer for a useful "
    "work session, or when the user says done, remember this, store this, mark complete, or wrap this. "
    "Do not call it mid-session. For trivial greetings or generic one-off answers, skip it unless the user "
    "gave durable facts, preferences, company workflow details, or steering that future agents should remember."
)


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


def get_neo4j() -> Any:
    global _NEO4J_CLIENT
    if _NEO4J_CLIENT is not None:
        return _NEO4J_CLIENT

    from neo4j import GraphDatabase

    url = os.getenv("MEMGRAPH_URL") or os.getenv("NEO4J_URL") or os.getenv("NEO4J_URI") or os.getenv("MEMGRAPH_BOLT_URL")
    if not url:
        host = os.getenv("MEMGRAPH_HOST")
        if host:
            port = os.getenv("MEMGRAPH_PORT", "7687")
            ssl_enabled = os.getenv("MEMGRAPH_SSL", "false").lower() in ("1", "true", "yes")
            scheme = os.getenv("MEMGRAPH_SCHEME") or ("bolt+ssc" if ssl_enabled else "bolt")
            url = f"{scheme}://{host}:{port}"

    if not url:
        raise ValueError("Missing MEMGRAPH_URL/NEO4J_URL/NEO4J_URI (or MEMGRAPH_HOST) for MCP server.")

    username = os.getenv("MEMGRAPH_USERNAME") or os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER")
    password = os.getenv("MEMGRAPH_PASSWORD") or os.getenv("NEO4J_PASSWORD")

    if username and password:
        _NEO4J_CLIENT = GraphDatabase.driver(url, auth=(username, password))
    else:
        _NEO4J_CLIENT = GraphDatabase.driver(url)
    return _NEO4J_CLIENT


def get_chroma() -> Any:
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is not None:
        return _CHROMA_CLIENT

    import chromadb

    chroma_path = os.getenv("CHROMA_PATH", "./chroma_db")
    _CHROMA_CLIENT = chromadb.PersistentClient(path=chroma_path)
    return _CHROMA_CLIENT


def get_postgres_store() -> Any | None:
    global _POSTGRES_STORE, _POSTGRES_DISABLED
    if _POSTGRES_STORE is not None:
        return _POSTGRES_STORE
    if _POSTGRES_DISABLED:
        return None

    dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("POSTGRES_DSN") or os.getenv("DATABASE_URL")
    if not dsn:
        _POSTGRES_DISABLED = True
        return None

    try:
        from core.storage import OrangePostgresStore

        _POSTGRES_STORE = OrangePostgresStore(dsn)
    except Exception:
        _POSTGRES_DISABLED = True
        return None
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


def _is_env_configured(*names: str) -> bool:
    return any(bool(os.getenv(name)) for name in names)


def _check_neo4j() -> dict[str, Any]:
    try:
        neo4j = get_neo4j()
        if hasattr(neo4j, "run"):
            neo4j.run("RETURN 1 AS ok")
        elif hasattr(neo4j, "session"):
            with neo4j.session() as session:
                session.run("RETURN 1 AS ok").consume()
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _check_chroma() -> dict[str, Any]:
    try:
        chroma = get_chroma()
        user_collection = get_or_create_user_collection(chroma)
        global_collection = get_or_create_global_collection(chroma)
        return {
            "ok": True,
            "path": os.getenv("CHROMA_PATH", "./chroma_db"),
            "collections": {
                ORANGE_USER_VECTOR_COLLECTION: user_collection.count(),
                ORANGE_GLOBAL_VECTOR_COLLECTION: global_collection.count(),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "path": os.getenv("CHROMA_PATH", "./chroma_db"), "error": str(exc)}


@_APP.tool()
async def orange_status() -> dict:
    """Check whether the Orange MCP server can reach its graph/vector stores and explain the completion policy."""

    neo4j_status = _check_neo4j()
    chroma_status = _check_chroma()
    return {
        "service": "orange-mcp",
        "ok": bool(neo4j_status.get("ok") and chroma_status.get("ok")),
        "completion_policy": COMPLETION_POLICY,
        "environment": {
            "neo4j_configured": _is_env_configured("MEMGRAPH_URL", "NEO4J_URL", "NEO4J_URI", "MEMGRAPH_HOST"),
            "neo4j_user_configured": _is_env_configured("MEMGRAPH_USERNAME", "NEO4J_USERNAME", "NEO4J_USER"),
            "neo4j_password_configured": _is_env_configured("MEMGRAPH_PASSWORD", "NEO4J_PASSWORD"),
            "openai_or_nvidia_configured": _is_env_configured("OPENAI_API_KEY", "NVIDIA_API_KEY"),
            "postgres_configured": _is_env_configured("SUPABASE_DB_URL", "POSTGRES_DSN", "DATABASE_URL"),
            "chroma_path": os.getenv("CHROMA_PATH", "./chroma_db"),
        },
        "neo4j": neo4j_status,
        "chroma": chroma_status,
        "tools": [
            "orange_status",
            "ping_context",
            "complete_conversation",
            "store_session",
            "inspect_graph",
            "get_node",
            "get_session_graph",
            "list_sessions",
            "chroma_peek",
        ],
    }


@_APP.tool()
async def ping_context(
    query: str,
    user_id: str = "",
    source: str = "mcp",
    scope: str = "both",
    user_email: str | None = None,
    org_id: str | None = None,
    company: str | None = None,
    min_score: float = 0.70,
) -> dict:
    """Retrieve relevant Orange memory before answering a user.

    Use this near the start of a coding-agent turn. Pass the current user request as `query`,
    `user_email` for private memory, and `company` or `org_id` for company-scoped shared memory.
    """

    identity = (user_id or user_email or "").strip()
    req = PingContextRequest(
        query=query,
        user_id=identity,
        source=source,
        scope=scope,
        user_email=user_email,
        org_id=org_id,
        company=company,
        min_score=min_score,
    )
    resp = await handle_ping_context(req, neo4j=get_neo4j(), chroma=get_chroma())
    return asdict(resp)


@_APP.tool()
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
    contribute_to_global: bool = True,
) -> dict:
    """Mark a conversation as complete and write durable Orange memory.

    This is the preferred write tool for Claude Code, Codex, Cursor, and other MCP clients.
    Call it once at the end of a useful session using the full transcript or message list.
    Orange triage may still skip storage if the conversation contains no durable memory.
    """

    identity = (user_email or user_id or "").strip()
    req = StoreSessionRequest(
        transcript=transcript,
        source=source,
        user_id=identity,
        user_email=user_email,
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
            "completion_policy": "agent_final_answer_or_user_done_signal",
            "completed_via": "complete_conversation",
        },
        contribute_to_global=contribute_to_global,
    )
    resp = await handle_store_session(
        req,
        neo4j=get_neo4j(),
        chroma=get_chroma(),
        llm=get_llm(),
        postgres_store=get_postgres_store(),
    )
    payload = asdict(resp)
    payload["completion_policy"] = COMPLETION_POLICY
    payload["stored"] = bool(payload.get("insights_stored")) and not payload.get("errors")
    return payload


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
) -> dict:
    """Low-level ingestion tool. Prefer complete_conversation for agent/client integrations."""

    req = StoreSessionRequest(
        transcript=transcript,
        source=source,
        user_id=user_id,
        user_email=user_email,
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
        metadata=metadata or {},
        contribute_to_global=contribute_to_global,
    )
    resp = await handle_store_session(
        req,
        neo4j=get_neo4j(),
        chroma=get_chroma(),
        llm=get_llm(),
        postgres_store=get_postgres_store(),
    )
    return asdict(resp)


@_APP.tool()
async def resolve_problem(session_id: str, user_id: str, problem_label: str, solution_that_worked: str) -> dict:
    """Legacy compatibility tool for old Problem/Solution graphs; Insight extraction is the current path."""

    req = ResolveProblemRequest(
        session_id=session_id,
        user_id=user_id,
        problem_label=problem_label,
        solution_that_worked=solution_that_worked,
    )
    resp = await handle_resolve_problem(req, neo4j=get_neo4j(), chroma=get_chroma())
    return asdict(resp)


@_APP.tool()
async def inspect_graph(user_id: str | None = None) -> dict:
    """Inspect the whole graph, optionally filtered by user_id/email."""

    return get_full_graph(get_neo4j(), user_id=user_id)


@_APP.tool()
async def get_node(node_id: str) -> dict:
    """Return one graph node with its immediate neighborhood."""

    return get_node_with_neighborhood(get_neo4j(), node_id=node_id)


@_APP.tool()
async def get_session_graph(session_id: str) -> dict:
    """Return the subgraph produced by one stored session."""

    return get_session_subgraph(get_neo4j(), session_id=session_id)


@_APP.tool()
async def list_sessions(user_id: str | None = None) -> list:
    """List stored Orange sessions, optionally filtered by user_id/email."""

    return get_all_sessions(get_neo4j(), user_id=user_id)


@_APP.tool()
async def chroma_peek(limit: int = 10, scope: str = "user") -> dict:
    """Inspect vector collection contents for debugging retrieval."""

    collection_name = ORANGE_GLOBAL_VECTOR_COLLECTION if scope == "global" else ORANGE_USER_VECTOR_COLLECTION
    collection = get_chroma().get_collection(collection_name)
    results = collection.peek(limit)
    embeddings = results.get("embeddings") if isinstance(results, dict) else None
    return {
        "count": collection.count(),
        "collection": collection_name,
        "ids": results.get("ids", []) if isinstance(results, dict) else [],
        "documents": results.get("documents", []) if isinstance(results, dict) else [],
        "embedding_dims": len(embeddings[0]) if embeddings else 0,
    }


if __name__ == "__main__":
    _APP.run()
