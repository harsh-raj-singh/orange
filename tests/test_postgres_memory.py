from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from core.graph_schema_v2 import Insight, Session, SourceType
from core.storage.postgres_memory import (
    PostgresMemoryRepository,
    scoped_session_node_id_for,
)


class FakeEmbeddingProvider:
    dimensions = 1536
    model = "text-embedding-3-small"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[0.125] * self.dimensions for _ in texts]


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class FakeConnection:
    def __init__(self, *, canonical: bool = False, organization_created: bool = True) -> None:
        self.canonical = canonical
        self.organization_created = organization_created
        self.executions: list[tuple[str, tuple[Any, ...]]] = []
        self.transactions = 0

    @contextmanager
    def transaction(self):
        self.transactions += 1
        yield

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeResult:
        self.executions.append((sql, params))
        if "orange:upsert-organization" in sql:
            return FakeResult([{"id": "00000000-0000-0000-0000-000000000020", "created": self.organization_created}])
        if "orange:find-user-for-upsert" in sql:
            return FakeResult()
        if "orange:insert-user-identity" in sql:
            return FakeResult([{"id": "00000000-0000-0000-0000-000000000010"}])
        if "orange:require-membership" in sql:
            return FakeResult([{"?column?": 1}]) if self.organization_created else FakeResult()
        if "orange:insert-memory-session" in sql:
            return FakeResult(
                [{"id": "00000000-0000-0000-0000-000000000030", "node_id": params[0]}]
            )
        if "orange:find-exact-insight" in sql:
            return FakeResult()
        if "orange:find-similar-insight" in sql:
            if not self.canonical:
                return FakeResult()
            return FakeResult(
                [
                    {
                        "id": "00000000-0000-0000-0000-000000000040",
                        "node_id": "existing-insight",
                        "what": "Use one transaction",
                        "why": "Avoid partial writes",
                        "how": "Write the session first",
                        "outcome": "exploratory",
                        "tags": ["postgres"],
                        "memory_kind": "technical_insight",
                        "similarity_score": 0.97,
                    }
                ]
            )
        if "orange:insert-insight" in sql:
            return FakeResult(
                [{"id": "00000000-0000-0000-0000-000000000050", "node_id": params[0]}]
            )
        return FakeResult()


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self.conn = connection

    @contextmanager
    def connection(self):
        yield self.conn


def _memory(*, how: str = "Commit graph and vector rows together") -> tuple[Session, Insight]:
    session = Session(
        node_id="session-retry-safe",
        source=SourceType.MCP,
        title="Postgres migration",
        summary="Move memory into one store",
        message_count=2,
    )
    insight = Insight(
        source=SourceType.MCP,
        what="Use one transaction",
        why="Avoid partial writes",
        how=how,
        display_label="Transactional memory",
        display_summary="Graph and embeddings commit together",
        tags=["postgres", "pgvector"],
    )
    return session, insight


def test_scoped_session_node_id_is_stable_and_owner_specific() -> None:
    first = scoped_session_node_id_for("user", "alice", "session-1")
    assert first == scoped_session_node_id_for("user", "alice", "session-1")
    assert first != scoped_session_node_id_for("user", "bob", "session-1")
    assert first != scoped_session_node_id_for("global", "alice", "session-1")


def test_upsert_writes_session_vector_insight_and_edge_in_one_transaction() -> None:
    conn = FakeConnection()
    embedder = FakeEmbeddingProvider()
    repository = PostgresMemoryRepository(pool=FakePool(conn), embedding_provider=embedder)
    session, insight = _memory()

    summary = repository.upsert_insights(
        session=session,
        user_id="alice",
        user_email="alice@example.com",
        insights=[insight],
    )

    assert conn.transactions == 1
    assert summary.sessions_written == 1
    assert summary.insights_stored == 1
    assert summary.edges_written == 1
    assert len(embedder.calls) == 1
    markers = [sql for sql, _ in conn.executions]
    assert any("orange:insert-memory-session" in sql for sql in markers)
    assert any("orange:insert-insight" in sql for sql in markers)
    assert any("orange:upsert-produced-edge" in sql for sql in markers)
    insert_params = next(params for sql, params in conn.executions if "orange:insert-insight" in sql)
    assert str(insert_params[21]).startswith("[")
    assert insert_params[22] == "text-embedding-3-small"


def test_canonical_merge_reembeds_merged_content_and_has_matching_sql_params() -> None:
    conn = FakeConnection(canonical=True)
    embedder = FakeEmbeddingProvider()
    repository = PostgresMemoryRepository(pool=FakePool(conn), embedding_provider=embedder)
    session, insight = _memory(how="Then insert the insight and edge")

    summary = repository.upsert_insights(
        session=session,
        user_id="alice",
        user_email="alice@example.com",
        insights=[insight],
    )

    assert summary.canonical_merges == 1
    assert summary.insights_stored == 0
    assert len(embedder.calls) == 2
    assert "Write the session first" in embedder.calls[1][0]
    assert "Then insert the insight and edge" in embedder.calls[1][0]
    sql, params = next(
        (sql, params) for sql, params in conn.executions if "orange:merge-canonical-insight" in sql
    )
    # Regression guard: seven placeholders and exactly seven values.
    assert sql.count("%s") == 7
    assert len(params) == 7
    assert str(params[3]).startswith("[")
    assert params[4] == "text-embedding-3-small"


def test_existing_organization_requires_explicit_membership() -> None:
    conn = FakeConnection(organization_created=False)
    repository = PostgresMemoryRepository(
        pool=FakePool(conn), embedding_provider=FakeEmbeddingProvider()
    )

    with pytest.raises(PermissionError, match="not a member"):
        repository.get_or_create_identity(
            user_id="mallory",
            user_email="mallory@example.com",
            org_id="existing-company",
        )
