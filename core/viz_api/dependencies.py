from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
_MEMORY_REPOSITORY: Any | None = None


def _postgres_dsn() -> str:
    return (
        os.getenv("POSTGRES_DSN")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()


def get_memory_repository() -> Any:
    """Return the process-wide Postgres graph/vector repository."""

    global _MEMORY_REPOSITORY
    if _MEMORY_REPOSITORY is not None:
        return _MEMORY_REPOSITORY
    dsn = _postgres_dsn()
    if not dsn:
        raise RuntimeError("POSTGRES_DSN is required for Orange memory storage.")
    from core.storage import PostgresMemoryRepository

    _MEMORY_REPOSITORY = PostgresMemoryRepository(dsn)
    return _MEMORY_REPOSITORY


def get_postgres_store() -> Any:
    """Backward-compatible name for call sites still being migrated."""

    return get_memory_repository()


def reset_memory_repository() -> None:
    """Close/reset the singleton in tests or controlled process shutdown."""

    global _MEMORY_REPOSITORY
    repository = _MEMORY_REPOSITORY
    _MEMORY_REPOSITORY = None
    if repository is not None:
        try:
            repository.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("postgres_repository_close_failed", extra={"error": str(exc)})
