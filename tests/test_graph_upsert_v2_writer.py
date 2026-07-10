from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.graph_schema_v2 import Insight, Session, SourceType
from core.graph_upsert.writer import GraphUpsertEngine


@dataclass
class FakeResult:
    record: dict[str, Any] | None = None

    def single(self) -> dict[str, Any] | None:
        return self.record


class FakeNeo4j:
    def __init__(self) -> None:
        self.sessions: dict[tuple[str, str], dict[str, Any]] = {}
        self.query_log: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> FakeResult:
        self.query_log.append((query, params))
        if "H4:MERGE_SESSION" in query:
            self.sessions[(params["node_id"], params["scope"])] = dict(params)
            return FakeResult({"node_id": params["node_id"]})
        return FakeResult(None)


class FakeChroma:
    def __init__(self, query_returns: dict[str, Any] | None = None) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.query_returns = query_returns or {"ids": [[]], "distances": [[]], "metadatas": [[]]}

    def query(self, **_kwargs: Any) -> dict[str, Any]:
        return self.query_returns

    def upsert(self, **kwargs: Any) -> None:
        self.upserts.append(kwargs)


def test_upsert_insights_merges_session_and_writes_vectors() -> None:
    neo4j = FakeNeo4j()
    chroma = FakeChroma()
    session = Session(node_id="session-insight", source=SourceType.CURSOR, title="v2", summary="summary", message_count=2)
    insight = Insight(
        memory_kind="technical_insight",
        what="auth failed after package upgrade",
        how="pinning the adapter restored the flow",
        outcome="resolved",
        display_label="OAuth adapter compatibility fix",
        display_summary="Pinning the adapter restored auth after an upgrade.",
        source=SourceType.CURSOR,
    )

    summary = GraphUpsertEngine(neo4j=neo4j, chroma=chroma).upsert_insights(
        session=session,
        user_id="dev@example.com",
        user_email="dev@example.com",
        insights=[insight],
    )

    assert summary.sessions_written == 1
    assert summary.insights_stored == 1
    assert any("MERGE (i:Insight" in query for query, _ in neo4j.query_log)
    assert any("MERGE (a)-[r:PRODUCED]->(b)" in query for query, _ in neo4j.query_log)
    assert neo4j.sessions[("session-insight", "user")]["source"] == "cursor"
    metadata = chroma.upserts[0]["metadatas"][0]
    assert metadata["node_type"] == "Insight"
    assert metadata["scope"] == "user"
    assert metadata["user_email"] == "dev@example.com"


def test_upsert_insights_global_vectors_omit_user_identity_and_audit_contributor() -> None:
    neo4j = FakeNeo4j()
    chroma = FakeChroma()
    session = Session(node_id="session-global", source=SourceType.CURSOR, title="global", summary="summary", message_count=1, org_id="acme")
    insight = Insight(
        memory_kind="company_fact",
        what="company uses markdown files for memory",
        display_label="Markdown company memory",
        display_summary="The company uses Markdown files as a memory source format.",
        source=SourceType.CURSOR,
    )

    GraphUpsertEngine(neo4j=neo4j, chroma=chroma).upsert_insights(
        session=session,
        user_id="dev@example.com",
        insights=[insight],
        scope="global",
        contributed_by="dev@example.com",
        org_id="acme",
        company="Acme",
    )

    insight_write = next(params for query, params in neo4j.query_log if "MERGE (i:Insight" in query)
    vector_metadata = chroma.upserts[0]["metadatas"][0]
    assert insight_write["scope"] == "global"
    assert insight_write["user_id"] is None
    assert insight_write["contributed_by"] == "dev@example.com"
    assert vector_metadata["scope"] == "global"
    assert vector_metadata["contributed_by"] == "dev@example.com"
    assert "user_id" not in vector_metadata
    assert "user_email" not in vector_metadata


def test_upsert_insights_merges_very_high_similarity_into_canonical_node() -> None:
    neo4j = FakeNeo4j()
    chroma = FakeChroma(
        {
            "ids": [["existing-vector"]],
            "distances": [[0.03]],
            "metadatas": [[
                {
                    "node_type": "Insight",
                    "scope": "user",
                    "user_id": "dev@example.com",
                    "neo4j_node_id": "existing-insight",
                }
            ]],
        }
    )
    session = Session(node_id="session-insight-merge", source=SourceType.CURSOR, title="merge", summary="summary", message_count=1)
    insight = Insight(
        memory_kind="technical_insight",
        what="same issue came back",
        how="updated the working mitigation",
        outcome="resolved",
        display_label="Repeated CORS issue",
        display_summary="The repeated issue should update the canonical insight.",
        source=SourceType.CURSOR,
    )

    summary = GraphUpsertEngine(neo4j=neo4j, chroma=chroma).upsert_insights(
        session=session,
        user_id="dev@example.com",
        insights=[insight],
        user_email="dev@example.com",
    )

    assert summary.insights_stored == 0
    assert summary.insights_skipped == 1
    assert chroma.upserts == []
    assert any("canonical_merge_count" in query and params["node_id"] == "existing-insight" for query, params in neo4j.query_log)
    assert any(
        params.get("to_id") == "existing-insight" and params.get("properties", {}).get("canonical_merge") is True
        for _, params in neo4j.query_log
    )
