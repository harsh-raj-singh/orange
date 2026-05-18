from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

import os
import json
import uuid
from contextvars import ContextVar
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
)
from core.mcp_server.handlers import handle_recall_memory, handle_resolve_problem, handle_store_session
from core.mcp_server.models import (
    RecallMemoryRequest,
    ResolveProblemRequest,
    StoreSessionRequest,
)
from core.mcp_server.tokens import decode_mcp_token, verify_mcp_token

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
_REQUEST_USER_EMAIL: ContextVar[str | None] = ContextVar("orange_request_user_email", default=None)
_REQUEST_BEARER_TOKEN: ContextVar[str | None] = ContextVar("orange_request_bearer_token", default=None)

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
    "Retrieves relevant memory from prior sessions via Chroma vector search + Neo4j graph hydration. "
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
    "Lightweight write to Neo4j only — no triage, no embedding. Use when something important just happened that you "
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
    "chroma_peek",
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


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _token_email_map() -> dict[str, str | None]:
    tokens: dict[str, str | None] = {}
    single_token = (os.getenv("ORANGE_MCP_BEARER_TOKEN") or os.getenv("ORANGE_MCP_API_KEY") or "").strip()
    if single_token:
        tokens[single_token] = (os.getenv("ORANGE_USER_EMAIL") or "").strip().lower() or None

    raw = (os.getenv("ORANGE_MCP_TOKEN_EMAILS") or "").strip()
    if not raw:
        return tokens

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        for token, email in parsed.items():
            clean_token = str(token or "").strip()
            if clean_token:
                tokens[clean_token] = str(email or "").strip().lower() or None
        return tokens

    for item in raw.split(","):
        if "=" not in item:
            continue
        token, email = item.split("=", 1)
        clean_token = token.strip()
        if clean_token:
            tokens[clean_token] = email.strip().lower() or None
    return tokens


def _signed_tokens_configured() -> bool:
    return bool((os.getenv("ORANGE_MCP_SIGNING_SECRET") or "").strip())


class BearerTokenMiddleware:
    """Minimal bearer-token auth for remote MCP transport."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        from starlette.responses import JSONResponse

        if _truthy_env("ORANGE_MCP_ALLOW_UNAUTHENTICATED"):
            await self.app(scope, receive, send)
            return

        tokens = _token_email_map()
        if not tokens and not _signed_tokens_configured():
            response = JSONResponse(
                {
                    "error": (
                        "ORANGE_MCP_SIGNING_SECRET, ORANGE_MCP_BEARER_TOKEN, "
                        "or ORANGE_MCP_TOKEN_EMAILS is required for remote MCP."
                    )
                },
                status_code=503,
            )
            await response(scope, receive, send)
            return

        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }
        auth = headers.get("authorization", "")
        prefix = "Bearer "
        token = auth[len(prefix) :].strip() if auth.startswith(prefix) else ""
        token_email = tokens.get(token)
        if token not in tokens:
            token_email = verify_mcp_token(token)
        if token_email is None and token not in tokens:
            response = JSONResponse({"error": "Unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return

        context_token = _REQUEST_USER_EMAIL.set(token_email)
        bearer_context_token = _REQUEST_BEARER_TOKEN.set(token or None)
        try:
            await self.app(scope, receive, send)
        finally:
            _REQUEST_USER_EMAIL.reset(context_token)
            _REQUEST_BEARER_TOKEN.reset(bearer_context_token)


def _http_middleware() -> list[Any]:
    from starlette.middleware import Middleware

    return [Middleware(BearerTokenMiddleware)]


def create_http_app(path: str = "/"):
    """Create the ASGI app used when Orange MCP is mounted on FastAPI."""

    return _APP.http_app(path=path, middleware=_http_middleware(), stateless_http=True)


def _default_user_email(value: str | None) -> str | None:
    cleaned = (value or "").strip().lower()
    if cleaned:
        return cleaned
    request_email = (_REQUEST_USER_EMAIL.get() or "").strip().lower()
    if request_email:
        return request_email
    env_email = (os.getenv("ORANGE_USER_EMAIL") or "").strip().lower()
    return env_email or None


def _run_neo4j(query: str, **params: Any) -> Any:
    neo4j = get_neo4j()
    if hasattr(neo4j, "run"):
        return neo4j.run(query, **params)
    if hasattr(neo4j, "session"):
        with neo4j.session() as session:
            result = session.run(query, **params)
            if hasattr(result, "data"):
                rows = result.data()
                return rows[0] if rows else None
            return result
    raise ValueError("Neo4j client must expose run(...) or session().")


def _single_record(result: Any) -> dict[str, Any] | None:
    if result is None:
        return None
    if isinstance(result, list):
        return result[0] if result else None
    if hasattr(result, "single"):
        record = result.single()
        return dict(record) if record else None
    if hasattr(result, "data"):
        rows = result.data()
        return rows[0] if rows else None
    if isinstance(result, dict):
        return result
    return None


def _configured_neo4j_uri() -> str | None:
    url = os.getenv("MEMGRAPH_URL") or os.getenv("NEO4J_URL") or os.getenv("NEO4J_URI") or os.getenv("MEMGRAPH_BOLT_URL")
    if url:
        return url.strip()
    host = os.getenv("MEMGRAPH_HOST")
    if not host:
        return None
    port = os.getenv("MEMGRAPH_PORT", "7687")
    ssl_enabled = os.getenv("MEMGRAPH_SSL", "false").lower() in ("1", "true", "yes")
    scheme = os.getenv("MEMGRAPH_SCHEME") or ("bolt+ssc" if ssl_enabled else "bolt")
    return f"{scheme}://{host}:{port}"


def _check_neo4j() -> dict[str, Any]:
    status: dict[str, Any] = {
        "reachable": False,
        "node_count": None,
        "expected_labels_present": False,
    }
    try:
        _run_neo4j("RETURN 1 AS ok")
        status["reachable"] = True
    except Exception:  # noqa: BLE001
        return status

    try:
        record = _single_record(_run_neo4j("MATCH (n) RETURN count(n) AS node_count"))
        status["node_count"] = int((record or {}).get("node_count"))
    except Exception:  # noqa: BLE001
        status["node_count"] = None

    try:
        record = _single_record(
            _run_neo4j(
                """
                MATCH (n)
                WITH labels(n) AS node_labels
                UNWIND node_labels AS label
                RETURN collect(DISTINCT label) AS labels
                """
            )
        )
        labels = set((record or {}).get("labels") or [])
        status["expected_labels_present"] = {"Session", "Entity", "Checkpoint"}.issubset(labels)
    except Exception:  # noqa: BLE001
        status["expected_labels_present"] = False

    return status


def _check_chroma() -> dict[str, Any]:
    status: dict[str, Any] = {
        "reachable": False,
        "collection_count": None,
    }
    try:
        chroma = get_chroma()
        status["reachable"] = True
        if hasattr(chroma, "count_collections"):
            status["collection_count"] = int(chroma.count_collections())
        elif hasattr(chroma, "list_collections"):
            status["collection_count"] = len(chroma.list_collections())
    except Exception:  # noqa: BLE001
        pass
    return status


def _auth_status() -> dict[str, Any]:
    token = (_REQUEST_BEARER_TOKEN.get() or "").strip()
    status: dict[str, Any] = {
        "token_present": bool(token),
        "token_valid": False,
        "user_email": None,
        "token_expires_at": None,
        "days_until_expiry": None,
    }
    if not token:
        return status

    payload = decode_mcp_token(token)
    if payload is not None:
        exp = int(payload.get("exp") or 0)
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
        seconds_until_expiry = max(0, exp - int(datetime.now(timezone.utc).timestamp()))
        status.update(
            {
                "token_valid": True,
                "user_email": payload.get("email"),
                "token_expires_at": expires_at.isoformat(),
                "days_until_expiry": seconds_until_expiry // 86400,
            }
        )
        return status

    token_email = _token_email_map().get(token)
    if token in _token_email_map():
        status.update(
            {
                "token_valid": True,
                "user_email": token_email,
            }
        )
    return status


def _mode() -> str:
    transport = (os.getenv("ORANGE_MCP_TRANSPORT") or "stdio").strip().lower()
    if _REQUEST_BEARER_TOKEN.get() or transport in {"http", "streamable-http", "sse"}:
        return "remote"
    return "local"


def _neo4j_shared_with_frontend() -> bool | None:
    frontend_uri = (os.getenv("FRONTEND_NEO4J_URI") or "").strip()
    if not frontend_uri:
        return None
    backend_uri = (_configured_neo4j_uri() or "").strip()
    return bool(backend_uri and backend_uri == frontend_uri)


def _status_warnings(
    *,
    neo4j_status: dict[str, Any],
    auth_status: dict[str, Any],
    neo4j_shared_with_frontend: bool | None,
) -> list[str]:
    warnings: list[str] = []
    if neo4j_shared_with_frontend is False:
        warnings.append(
            "Neo4j instance differs from frontend config. Nodes written via MCP will not appear on the website. "
            "Set ORANGE_NEO4J_URI to the same instance used by Vercel."
        )
    days_until_expiry = auth_status.get("days_until_expiry")
    if days_until_expiry is not None and int(days_until_expiry) <= 7:
        warnings.append(f"MCP token expires in {days_until_expiry} days. Re-authenticate at /mcp.")
    if neo4j_status.get("expected_labels_present") is False:
        warnings.append(
            "Neo4j graph is missing expected labels (Session, Entity, Checkpoint). "
            "Run schema initialization or complete at least one full session."
        )
    return warnings


@_APP.tool()
async def orange_status() -> dict:
    """Return structured Orange MCP health, auth, schema, and tool information."""

    neo4j_status = _check_neo4j()
    chroma_status = _check_chroma()
    auth_status = _auth_status()
    neo4j_shared_with_frontend = _neo4j_shared_with_frontend()
    return {
        "neo4j": neo4j_status,
        "chroma": chroma_status,
        "auth": auth_status,
        "mode": _mode(),
        "neo4j_shared_with_frontend": neo4j_shared_with_frontend,
        "warnings": _status_warnings(
            neo4j_status=neo4j_status,
            auth_status=auth_status,
            neo4j_shared_with_frontend=neo4j_shared_with_frontend,
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
    identity = (user_id or resolved_email or "").strip()
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
    resp = await handle_recall_memory(req, neo4j=get_neo4j(), chroma=get_chroma())
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
    identity = (resolved_email or user_id or "").strip()
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
            "completion_policy": "agent_final_answer_or_user_done_signal",
            "completed_via": "complete_conversation",
        },
        contribute_to_global=contribute_to_global,
        summary=summary,
        key_entities=key_entities or [],
        decisions=decisions or [],
        problems_solved=problems_solved or [],
        worth_storing=worth_storing,
        session_duration_turns=session_duration_turns,
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


@_APP.tool(description=CHECKPOINT_CONTEXT_DESCRIPTION)
async def checkpoint_context(
    note: str,
    user_email: str | None = None,
    user_id: str = "",
    org_id: str | None = None,
    company: str | None = None,
    source: str = "mcp",
) -> dict:
    """Write a lightweight mid-session checkpoint to Neo4j only."""

    cleaned_note = (note or "").strip()
    if not cleaned_note:
        raise ValueError("note is required")
    resolved_email = _default_user_email(user_email)
    timestamp = datetime.now(timezone.utc).isoformat()
    params = {
        "node_id": f"checkpoint_{uuid.uuid4().hex}",
        "type": "checkpoint",
        "note": cleaned_note,
        "timestamp": timestamp,
        "user_email": resolved_email,
        "user_id": (user_id or resolved_email or "").strip(),
        "org_id": org_id,
        "company": company,
        "source": source,
    }
    _run_neo4j(
        """
        CREATE (c:Checkpoint:Entity {
          node_id: $node_id,
          type: $type,
          note: $note,
          timestamp: $timestamp,
          user_email: $user_email,
          user_id: $user_id,
          org_id: $org_id,
          company: $company,
          source: $source
        })
        """,
        **params,
    )
    return {"checkpointed": True, "timestamp": timestamp}


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
