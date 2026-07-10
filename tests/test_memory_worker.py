from __future__ import annotations

import asyncio

from core.ingestion import SessionIngestionRequest, normalize_ingestion_request
from core.storage import worker as worker_module


class FakeRepository:
    def __init__(self) -> None:
        self.finished: list[dict] = []
        self.statuses: list[tuple[str, str]] = []
        self.normalized = normalize_ingestion_request(
            SessionIngestionRequest(
                source="mcp",
                session_id="session-worker",
                user_id="user-1",
                user_email="dev@example.com",
                transcript="Turn 1 [user]: remember the Postgres worker",
                metadata={"worth_storing": True, "contribute_to_global": False},
            )
        )

    def claim_memory_write_jobs(self, worker_id, *, limit, lease_seconds):
        return [{"id": "job-1", "ingestion_id": "ingestion-1", "status": "running"}]

    def load_normalized_session(self, ingestion_id):
        assert ingestion_id == "ingestion-1"
        return self.normalized

    def finish_memory_write_job(self, job_id, worker_id, **kwargs):
        self.finished.append({"job_id": job_id, "worker_id": worker_id, **kwargs})
        return {"status": "succeeded" if kwargs["succeeded"] else "retrying"}

    def mark_session_status(self, *, ingestion_id, status):
        self.statuses.append((ingestion_id, status))


def test_worker_claims_processes_and_finishes_job(monkeypatch) -> None:
    repository = FakeRepository()
    captured = {}

    async def fake_pipeline(**kwargs):
        captured.update(kwargs)
        return {"insights_stored": 2, "errors": []}

    monkeypatch.setattr(worker_module, "run_extraction_pipeline", fake_pipeline)
    worker = worker_module.MemoryWriteWorker(repository, concurrency=1)

    processed = asyncio.run(worker.run_once())

    assert processed == 1
    assert captured["memory_repository"] is repository
    assert captured["source_ingestion_id"] == "ingestion-1"
    assert captured["force_worth_storing"] is True
    assert captured["contribute_to_global"] is False
    assert repository.finished[0]["succeeded"] is True
    assert repository.finished[0]["result"]["insights_stored"] == 2
    assert repository.statuses == [("ingestion-1", "processed")]


def test_worker_records_retryable_failure(monkeypatch) -> None:
    repository = FakeRepository()

    async def failing_pipeline(**_kwargs):
        raise RuntimeError("extractor unavailable")

    monkeypatch.setattr(worker_module, "run_extraction_pipeline", failing_pipeline)
    worker = worker_module.MemoryWriteWorker(repository, concurrency=1)

    processed = asyncio.run(worker.run_once())

    assert processed == 1
    assert repository.finished[0]["succeeded"] is False
    assert "extractor unavailable" in repository.finished[0]["error"]
    assert repository.statuses == []
