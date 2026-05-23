from __future__ import annotations

import re

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.graph_queries.neo4j_queries import (
    filter_graph_by_scope,
    get_all_problems,
    get_all_sessions,
    get_full_graph,
    get_node_with_neighborhood,
    get_nodes_since,
    get_problem_chain,
    get_relationship_stats,
    get_session_subgraph,
)
from core.viz_api.dependencies import get_neo4j

router = APIRouter()


def _clean_org_id(value: str | None) -> str | None:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return cleaned or None


def _effective_scope(
    *,
    requested_scope: str,
    user_id: str | None,
    user_email: str | None,
    org_id: str | None,
) -> str | None:
    has_user_identity = bool((user_email or "").strip() or (user_id or "").strip())
    has_org_identity = bool((org_id or "").strip())

    if requested_scope == "user":
        return "user" if has_user_identity else None
    if requested_scope == "global":
        return "global" if has_org_identity else None
    if has_user_identity and has_org_identity:
        return "both"
    if has_user_identity:
        return "user"
    if has_org_identity:
        return "global"
    return None


@router.get("/full")
async def full_graph(
    user_id: str | None = None,
    user_email: str | None = None,
    org_id: str | None = None,
    company: str | None = None,
    scope: str = "both",
) -> JSONResponse:
    clean_org_id = _clean_org_id(org_id or company)
    effective_scope = _effective_scope(
        requested_scope=scope,
        user_id=user_id,
        user_email=user_email,
        org_id=clean_org_id,
    )
    if effective_scope is None:
        return JSONResponse({"nodes": [], "edges": []})

    try:
        raw_graph = get_full_graph(
            get_neo4j(),
            user_id=user_id,
            user_email=user_email,
            org_id=clean_org_id,
            scope=effective_scope,
        )
        return JSONResponse(
            filter_graph_by_scope(
                raw_graph,
                user_id=user_id,
                user_email=user_email,
                org_id=clean_org_id,
                scope=scope,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/nodes/{node_id}/neighborhood")
async def node_neighborhood(
    node_id: str,
    user_id: str | None = None,
    user_email: str | None = None,
    org_id: str | None = None,
    company: str | None = None,
    scope: str = "both",
) -> JSONResponse:
    clean_org_id = _clean_org_id(org_id or company)
    effective_scope = _effective_scope(
        requested_scope=scope,
        user_id=user_id,
        user_email=user_email,
        org_id=clean_org_id,
    )
    if effective_scope is None:
        return JSONResponse({"nodes": [], "edges": []})

    try:
        raw_graph = get_node_with_neighborhood(get_neo4j(), node_id=node_id)
        return JSONResponse(
            filter_graph_by_scope(
                raw_graph,
                user_id=user_id,
                user_email=user_email,
                org_id=clean_org_id,
                scope=scope,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/sessions")
async def sessions(user_id: str | None = None) -> JSONResponse:
    try:
        data = get_all_sessions(get_neo4j(), user_id=user_id)
        return JSONResponse(data)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/sessions/{session_id}")
async def session_graph(session_id: str) -> JSONResponse:
    try:
        data = get_session_subgraph(get_neo4j(), session_id=session_id)
        return JSONResponse(data)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/problems")
async def problems(user_id: str | None = None) -> JSONResponse:
    try:
        data = get_all_problems(get_neo4j(), user_id=user_id)
        return JSONResponse(data)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/problems/{canonical_label}/chain")
async def problem_chain(canonical_label: str, user_id: str) -> JSONResponse:
    try:
        data = get_problem_chain(get_neo4j(), canonical_label=canonical_label, user_id=user_id)
        return JSONResponse(data)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/relationships")
async def relationship_stats() -> JSONResponse:
    try:
        data = get_relationship_stats(get_neo4j())
        return JSONResponse(data)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/updates")
async def graph_updates(since: float, user_id: str | None = None) -> JSONResponse:
    try:
        data = get_nodes_since(get_neo4j(), since_timestamp=since, user_id=user_id)
        return JSONResponse(data)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})
