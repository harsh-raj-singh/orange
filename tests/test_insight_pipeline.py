from __future__ import annotations

import asyncio

from core.agents.extraction_outputs import InsightDraft, TriageDecision
from core.agents.orchestrator import run_extraction_pipeline
from core.graph_schema_v2 import SourceType


def test_triage_blocks_low_signal_session(monkeypatch, mock_neo4j, mock_chroma) -> None:
    async def fake_triage(_transcript: str) -> TriageDecision:
        return TriageDecision(worth_storing=False, reason="generic answer")

    async def fail_extract(_transcript: str) -> list[InsightDraft]:
        raise AssertionError("extractor should not run when triage blocks")

    monkeypatch.setattr("core.agents.orchestrator.run_triage_agent", fake_triage)
    monkeypatch.setattr("core.agents.orchestrator.extract_insights", fail_extract)

    result = asyncio.run(
        run_extraction_pipeline(
            session_id="session-low-signal",
            user_id="dev@example.com",
            transcript="Turn 1 [user]: hey how do I reverse a string in python\nTurn 2 [assistant]: use s[::-1]",
            source=SourceType.CURSOR,
            neo4j_client=mock_neo4j,
            chroma_client=mock_chroma,
            contribute_to_global=False,
        )
    )

    assert result["insights_stored"] == 0
    assert result["skipped_reason"] == "generic answer"
    assert mock_chroma.upserts == []
    assert not any("MERGE (i:Insight" in query for query, _ in mock_neo4j.query_log)


def test_pipeline_writes_unified_insight(monkeypatch, mock_neo4j, mock_chroma) -> None:
    async def fake_triage(_transcript: str) -> TriageDecision:
        return TriageDecision(worth_storing=True, reason="debugging produced durable learning")

    async def fake_extract(_transcript: str) -> list[InsightDraft]:
        return [
            InsightDraft(
                what="auth failed after package upgrade",
                why="oauth adapter incompatible with new framework major",
                how="pinned adapter to previous major version",
                outcome="resolved",
                tags=["oauth", "compatibility"],
                display_label="OAuth adapter compatibility fix",
                display_summary="Auth failed after a framework upgrade. Pinning the adapter restored the flow.",
            )
        ]

    monkeypatch.setattr("core.agents.orchestrator.run_triage_agent", fake_triage)
    monkeypatch.setattr("core.agents.orchestrator.extract_insights", fake_extract)

    result = asyncio.run(
        run_extraction_pipeline(
            session_id="session-insight",
            user_id="dev@example.com",
            transcript="Turn 1 [user]: auth failed after package upgrade\nTurn 2 [assistant]: pin adapter version; it worked",
            source=SourceType.CURSOR,
            neo4j_client=mock_neo4j,
            chroma_client=mock_chroma,
            contribute_to_global=False,
        )
    )

    assert result["insights_stored"] == 1
    assert any("MERGE (i:Insight" in query for query, _ in mock_neo4j.query_log)
    assert any("MERGE (a)-[r:PRODUCED]->(b)" in query for query, _ in mock_neo4j.query_log)
    metadata = mock_chroma.upserts[0]["metadatas"][0]
    assert metadata["node_type"] == "Insight"
    assert metadata["outcome"] == "resolved"
    assert metadata["tags"] == "oauth,compatibility"
