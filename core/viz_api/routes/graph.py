from __future__ import annotations

import asyncio
import logging
import re
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from core.auth import AuthenticatedIdentity, require_request_identity
from core.viz_api.dependencies import get_memory_repository

router = APIRouter()
logger = logging.getLogger(__name__)
NO_STORE_HEADERS = {"Cache-Control": "no-store, max-age=0"}


def _clean_org_id(value: str | None) -> str | None:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return cleaned or None


def _scope(value: str) -> str:
    cleaned = str(value or "both").strip().lower()
    if cleaned not in {"user", "global", "both"}:
        raise ValueError("scope must be user, global, or both")
    return cleaned


async def _repository_call(call: Callable[..., Any], /, **kwargs: Any) -> JSONResponse:
    try:
        result = await asyncio.to_thread(call, **kwargs)
        return JSONResponse(result, headers=NO_STORE_HEADERS)
    except PermissionError as exc:
        return JSONResponse(
            status_code=403,
            content={"error": str(exc)},
            headers=NO_STORE_HEADERS,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": str(exc)},
            headers=NO_STORE_HEADERS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("postgres_graph_read_failed", extra={"error": str(exc)})
        return JSONResponse(
            status_code=500,
            content={"error": "Orange could not read the memory graph."},
            headers=NO_STORE_HEADERS,
        )


@router.get("/full")
async def full_graph(
    identity: Annotated[AuthenticatedIdentity, Depends(require_request_identity)],
    org_id: str | None = None,
    company: str | None = None,
    scope: str = "both",
    limit: int = 1000,
    offset: int = 0,
    user_id: str | None = None,
    user_email: str | None = None,
) -> JSONResponse:
    del user_id, user_email  # Identity always comes from the verified bearer.
    repository = get_memory_repository()
    return await _repository_call(
        repository.get_full_graph,
        user_id=identity.subject,
        user_email=identity.email,
        org_id=_clean_org_id(org_id or company),
        scope=_scope(scope),
        limit=limit,
        offset=offset,
    )


@router.get("/version")
async def graph_version(
    identity: Annotated[AuthenticatedIdentity, Depends(require_request_identity)],
    org_id: str | None = None,
    company: str | None = None,
    scope: str = "both",
    user_id: str | None = None,
    user_email: str | None = None,
) -> JSONResponse:
    del user_id, user_email
    repository = get_memory_repository()
    return await _repository_call(
        repository.get_graph_version,
        user_id=identity.subject,
        user_email=identity.email,
        org_id=_clean_org_id(org_id or company),
        scope=_scope(scope),
    )


@router.get("/nodes/{node_id}/neighborhood")
async def node_neighborhood(
    node_id: str,
    identity: Annotated[AuthenticatedIdentity, Depends(require_request_identity)],
    org_id: str | None = None,
    company: str | None = None,
    scope: str = "both",
    limit: int = 100,
    user_id: str | None = None,
    user_email: str | None = None,
) -> JSONResponse:
    del user_id, user_email
    repository = get_memory_repository()
    return await _repository_call(
        repository.get_node_with_neighborhood,
        node_id=node_id,
        user_id=identity.subject,
        user_email=identity.email,
        org_id=_clean_org_id(org_id or company),
        scope=_scope(scope),
        limit=limit,
    )


@router.get("/sessions")
async def sessions(
    identity: Annotated[AuthenticatedIdentity, Depends(require_request_identity)],
    org_id: str | None = None,
    company: str | None = None,
    scope: str = "both",
    limit: int = 100,
    offset: int = 0,
    user_id: str | None = None,
) -> JSONResponse:
    del user_id
    repository = get_memory_repository()
    return await _repository_call(
        repository.list_sessions,
        user_id=identity.subject,
        user_email=identity.email,
        org_id=_clean_org_id(org_id or company),
        scope=_scope(scope),
        limit=limit,
        offset=offset,
    )


@router.get("/sessions/{session_id}")
async def session_graph(
    session_id: str,
    identity: Annotated[AuthenticatedIdentity, Depends(require_request_identity)],
    org_id: str | None = None,
    company: str | None = None,
    scope: str = "both",
) -> JSONResponse:
    repository = get_memory_repository()
    return await _repository_call(
        repository.get_session_subgraph,
        session_id=session_id,
        user_id=identity.subject,
        user_email=identity.email,
        org_id=_clean_org_id(org_id or company),
        scope=_scope(scope),
    )
