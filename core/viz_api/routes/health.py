from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.viz_api.dependencies import get_memory_repository

router = APIRouter()
logger = logging.getLogger(__name__)


def _postgres_health() -> dict[str, Any]:
    repository = get_memory_repository()
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
    return {
        "reachable": True,
        "pgvector_version": row.get("pgvector_version"),
        "session_count": int(row.get("session_count") or 0),
        "insight_count": int(row.get("insight_count") or 0),
        "queued_jobs": int(row.get("queued_jobs") or 0),
        "dead_letter_jobs": int(row.get("dead_letter_jobs") or 0),
    }


@router.get("/")
async def root() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "orange-backend",
            "storage": "supabase-postgres-pgvector",
            "health": "/health",
            "deep_health": "/health/deep",
            "mcp": "/mcp",
        }
    )


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "orange-backend"})


@router.get("/health/deep")
async def deep_health() -> JSONResponse:
    try:
        postgres = await asyncio.to_thread(_postgres_health)
    except Exception as exc:  # noqa: BLE001
        logger.warning("postgres_health_check_failed", extra={"error": str(exc)})
        postgres = {"reachable": False, "pgvector_version": None}
    healthy = bool(postgres.get("reachable") and postgres.get("pgvector_version"))
    return JSONResponse(
        {"postgres": postgres, "status": "healthy" if healthy else "degraded"},
        status_code=200 if healthy else 503,
    )
