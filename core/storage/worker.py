from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

from core.agents.orchestrator import run_extraction_pipeline

logger = logging.getLogger(__name__)


class MemoryWriteWorker:
    """Recoverable worker for Postgres-backed extraction jobs."""

    def __init__(
        self,
        repository: Any,
        *,
        llm_factory: Callable[[], Any] | None = None,
        concurrency: int = 2,
        poll_interval: float = 2.0,
        lease_seconds: int = 900,
    ) -> None:
        self.repository = repository
        self.llm_factory = llm_factory
        self.concurrency = min(max(int(concurrency), 1), 8)
        self.poll_interval = max(float(poll_interval), 0.25)
        self.lease_seconds = min(max(int(lease_seconds), 60), 3600)
        self.worker_id = (
            f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        )
        self._stopping = asyncio.Event()

    async def run(self) -> None:
        logger.info(
            "memory_worker_started",
            extra={"worker_id": self.worker_id, "concurrency": self.concurrency},
        )
        while not self._stopping.is_set():
            try:
                processed = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "memory_worker_poll_failed",
                    extra={"worker_id": self.worker_id, "error": str(exc)},
                )
                processed = 0
            if not processed:
                try:
                    await asyncio.wait_for(
                        self._stopping.wait(), timeout=self.poll_interval
                    )
                except TimeoutError:
                    pass
        logger.info("memory_worker_stopped", extra={"worker_id": self.worker_id})

    async def run_once(self) -> int:
        jobs = await asyncio.to_thread(
            self.repository.claim_memory_write_jobs,
            self.worker_id,
            limit=self.concurrency,
            lease_seconds=self.lease_seconds,
        )
        if not jobs:
            return 0
        await asyncio.gather(*(self._process_job(job) for job in jobs))
        return len(jobs)

    async def _process_job(self, job: dict[str, Any]) -> None:
        job_id = str(job.get("id") or "")
        ingestion_id = str(job.get("ingestion_id") or "")
        if not job_id or not ingestion_id:
            logger.error("memory_worker_invalid_job", extra={"job": job})
            return

        try:
            normalized = await asyncio.to_thread(
                self.repository.load_normalized_session, ingestion_id
            )
            identity = (normalized.user_email or normalized.user_id or "").strip()
            if not identity:
                raise ValueError("Stored ingestion has no user identity.")
            metadata = normalized.metadata
            result = await run_extraction_pipeline(
                session_id=normalized.session_id,
                user_id=identity,
                transcript=normalized.transcript,
                source=normalized.source,
                normalized_session=normalized,
                memory_repository=self.repository,
                contribute_to_global=bool(metadata.get("contribute_to_global", True)),
                pii_llm=self.llm_factory() if self.llm_factory else None,
                force_worth_storing=metadata.get("worth_storing") is True,
                scope_override=(
                    str(metadata.get("scope_override") or "").strip() or None
                ),
                source_ingestion_id=ingestion_id,
            )
            await asyncio.to_thread(
                self.repository.finish_memory_write_job,
                job_id,
                self.worker_id,
                succeeded=True,
                result=result,
            )
            await asyncio.to_thread(
                self.repository.mark_session_status,
                ingestion_id=ingestion_id,
                status="processed",
            )
            logger.info(
                "memory_worker_job_succeeded",
                extra={
                    "job_id": job_id,
                    "ingestion_id": ingestion_id,
                    "insights_stored": result.get("insights_stored", 0),
                },
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "memory_worker_job_failed",
                extra={"job_id": job_id, "ingestion_id": ingestion_id, "error": str(exc)},
            )
            try:
                finished = await asyncio.to_thread(
                    self.repository.finish_memory_write_job,
                    job_id,
                    self.worker_id,
                    succeeded=False,
                    error=str(exc),
                    retry_delay_seconds=30,
                )
                if finished.get("status") in {"failed", "dead_letter"}:
                    await asyncio.to_thread(
                        self.repository.mark_session_status,
                        ingestion_id=ingestion_id,
                        status="failed",
                    )
            except Exception as finish_exc:  # noqa: BLE001
                logger.exception(
                    "memory_worker_job_finish_failed",
                    extra={"job_id": job_id, "error": str(finish_exc)},
                )

    def stop(self) -> None:
        self._stopping.set()


@asynccontextmanager
async def memory_worker_lifespan(
    repository: Any | None,
    *,
    llm_factory: Callable[[], Any] | None = None,
) -> AsyncIterator[None]:
    if repository is None:
        yield
        return
    worker = MemoryWriteWorker(
        repository,
        llm_factory=llm_factory,
        concurrency=int(os.getenv("ORANGE_MEMORY_WORKER_CONCURRENCY", "2")),
        poll_interval=float(os.getenv("ORANGE_MEMORY_WORKER_POLL_SECONDS", "2")),
        lease_seconds=int(os.getenv("ORANGE_MEMORY_JOB_LEASE_SECONDS", "900")),
    )
    task = asyncio.create_task(worker.run(), name="orange-memory-worker")
    try:
        yield
    finally:
        worker.stop()
        try:
            await asyncio.wait_for(task, timeout=10)
        except TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


__all__ = ["MemoryWriteWorker", "memory_worker_lifespan"]
