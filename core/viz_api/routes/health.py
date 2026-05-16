from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.viz_api.dependencies import get_chroma, get_neo4j

router = APIRouter()


def _run_neo4j_ping(neo4j: object) -> None:
    if hasattr(neo4j, "run"):
        neo4j.run("RETURN 1 AS ok")
        return
    if hasattr(neo4j, "session"):
        with neo4j.session() as session:
            session.run("RETURN 1 AS ok").single()
        return
    raise ValueError("Neo4j client must expose run(...) or session().")


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "orange-backend"})


@router.get("/health/deep")
async def deep_health() -> JSONResponse:
    neo4j_status = "ok"
    chroma_status = "ok"

    try:
        _run_neo4j_ping(get_neo4j())
    except Exception as exc:  # noqa: BLE001
        neo4j_status = f"error: {exc}"

    try:
        get_chroma().heartbeat()
    except Exception as exc:  # noqa: BLE001
        chroma_status = f"error: {exc}"

    status = "healthy" if neo4j_status == "ok" and chroma_status == "ok" else "degraded"
    return JSONResponse({"neo4j": neo4j_status, "chroma": chroma_status, "status": status})
