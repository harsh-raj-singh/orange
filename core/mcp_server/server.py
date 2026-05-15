from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

import asyncio
import os
from dataclasses import asdict
from typing import Any

from core.graph_queries.neo4j_queries import (
    get_all_sessions,
    get_full_graph,
    get_node_with_neighborhood,
    get_session_subgraph,
)
from core.graph_upsert.dedup import ORANGE_NODE_VECTOR_COLLECTION
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

    url = os.getenv("MEMGRAPH_URL") or os.getenv("NEO4J_URL") or os.getenv("MEMGRAPH_BOLT_URL")
    if not url:
        host = os.getenv("MEMGRAPH_HOST")
        if host:
            port = os.getenv("MEMGRAPH_PORT", "7687")
            ssl_enabled = os.getenv("MEMGRAPH_SSL", "false").lower() in ("1", "true", "yes")
            scheme = os.getenv("MEMGRAPH_SCHEME") or ("bolt+ssc" if ssl_enabled else "bolt")
            url = f"{scheme}://{host}:{port}"

    if not url:
        raise ValueError("Missing MEMGRAPH_URL/NEO4J_URL (or MEMGRAPH_HOST) for MCP server.")

    username = os.getenv("MEMGRAPH_USERNAME") or os.getenv("NEO4J_USERNAME")
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


def get_llm() -> Any:
    global _LLM_CLIENT
    if _LLM_CLIENT is not None:
        return _LLM_CLIENT

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("NVIDIA_API_KEY")
    if not api_key:
        _LLM_CLIENT = None
        return _LLM_CLIENT

    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("NVIDIA_BASE_URL")
    model = os.getenv("OPENAI_MODEL") or os.getenv("NVIDIA_MODEL") or "meta/llama-3.1-8b-instruct"
    _LLM_CLIENT = OpenAILLMAdapter(api_key=api_key, model=model, base_url=base_url)
    return _LLM_CLIENT


@_APP.tool()
async def ping_context(query: str, user_id: str, source: str) -> dict:
    req = PingContextRequest(query=query, user_id=user_id, source=source)
    resp = await handle_ping_context(req, neo4j=get_neo4j(), chroma=get_chroma())
    return asdict(resp)


@_APP.tool()
async def store_session(
    transcript: str,
    source: str,
    user_id: str = "",
    session_id: str = "",
    org_id: str | None = None,
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
) -> dict:
    req = StoreSessionRequest(
        transcript=transcript,
        source=source,
        user_id=user_id,
        session_id=session_id,
        external_session_id=external_session_id,
        org_id=org_id,
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
    )
    resp = await handle_store_session(req, neo4j=get_neo4j(), chroma=get_chroma(), llm=get_llm())
    return asdict(resp)


@_APP.tool()
async def resolve_problem(session_id: str, user_id: str, problem_label: str, solution_that_worked: str) -> dict:
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
    return get_full_graph(get_neo4j(), user_id=user_id)


@_APP.tool()
async def get_node(node_id: str) -> dict:
    return get_node_with_neighborhood(get_neo4j(), node_id=node_id)


@_APP.tool()
async def get_session_graph(session_id: str) -> dict:
    return get_session_subgraph(get_neo4j(), session_id=session_id)


@_APP.tool()
async def list_sessions(user_id: str | None = None) -> list:
    return get_all_sessions(get_neo4j(), user_id=user_id)


@_APP.tool()
async def chroma_peek(limit: int = 10) -> dict:
    collection = get_chroma().get_collection(ORANGE_NODE_VECTOR_COLLECTION)
    results = collection.peek(limit)
    embeddings = results.get("embeddings") if isinstance(results, dict) else None
    return {
        "count": collection.count(),
        "ids": results.get("ids", []) if isinstance(results, dict) else [],
        "documents": results.get("documents", []) if isinstance(results, dict) else [],
        "embedding_dims": len(embeddings[0]) if embeddings else 0,
    }


if __name__ == "__main__":
    _APP.run()
