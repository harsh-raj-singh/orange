from __future__ import annotations

import asyncio

from core.agents.extraction_outputs import InsightDraft, TriageDecision
from core.agents.orchestrator import run_extraction_pipeline
from core.ingestion import SessionIngestionRequest, normalize_ingestion_request
from core.graph_schema_v2 import SourceType


def test_triage_blocks_low_signal_session(monkeypatch, mock_neo4j, mock_chroma) -> None:
    async def fake_triage(_transcript: str, **_kwargs) -> TriageDecision:
        return TriageDecision(worth_storing=False, reason="generic answer")

    async def fail_extract(_transcript: str, **_kwargs) -> list[InsightDraft]:
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
    async def fake_triage(_transcript: str, **_kwargs) -> TriageDecision:
        return TriageDecision(worth_storing=True, reason="debugging produced durable learning")

    async def fake_extract(_transcript: str, **_kwargs) -> list[InsightDraft]:
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


def test_user_and_company_pipelines_are_independent(monkeypatch, mock_neo4j, mock_chroma) -> None:
    async def fake_triage(_transcript: str, **kwargs) -> TriageDecision:
        if kwargs.get("scope") == "global":
            return TriageDecision(worth_storing=True, reason="company fact")
        return TriageDecision(worth_storing=True, reason="user steering")

    async def fake_extract(_transcript: str, **kwargs) -> list[InsightDraft]:
        if kwargs.get("scope") == "global":
            return [
                InsightDraft(
                    what="company uses markdown files for memory",
                    why=None,
                    how=None,
                    outcome="exploratory",
                    memory_kind="company_fact",
                    tags=["markdown", "memory"],
                    display_label="Markdown files for company memory",
                    display_summary="The company uses Markdown files as a memory source format.",
                )
            ]
        return [
            InsightDraft(
                what="future website work should keep Orange dark and Linear-like",
                why=None,
                how=None,
                outcome="exploratory",
                memory_kind="steering",
                tags=["website", "design-steering"],
                display_label="Dark Linear-like website steering",
                display_summary="Future Orange website work should preserve the dark, premium Linear-like direction.",
            )
        ]

    monkeypatch.setattr("core.agents.orchestrator.run_triage_agent", fake_triage)
    monkeypatch.setattr("core.agents.orchestrator.extract_insights", fake_extract)

    transcript = "Turn 1 [user]: our company uses .md files for memory. Also make the Orange website darker and more Linear-like."
    normalized = normalize_ingestion_request(
        SessionIngestionRequest(
            source="cursor",
            session_id="session-company-fact",
            user_id="dev@example.com",
            user_email="dev@example.com",
            org_id="acme",
            transcript=transcript,
            metadata={"profile": {"company": "Acme"}},
        )
    )

    result = asyncio.run(
        run_extraction_pipeline(
            session_id="session-company-fact",
            user_id="dev@example.com",
            transcript=transcript,
            source=SourceType.CURSOR,
            neo4j_client=mock_neo4j,
            chroma_client=mock_chroma,
            contribute_to_global=True,
            normalized_session=normalized,
        )
    )

    assert result["insights_stored"] == 2
    metadatas = [upsert["metadatas"][0] for upsert in mock_chroma.upserts]
    assert {metadata["scope"] for metadata in metadatas} == {"user", "global"}
    assert any(metadata["memory_kind"] == "steering" and metadata["scope"] == "user" for metadata in metadatas)
    assert any(metadata["memory_kind"] == "company_fact" and metadata["scope"] == "global" for metadata in metadatas)


def test_user_and_company_pipelines_run_concurrently(monkeypatch, mock_neo4j, mock_chroma) -> None:
    active_triage_calls = 0
    max_active_triage_calls = 0
    triage_scopes: list[str] = []

    async def fake_scrub(transcript: str, **_kwargs) -> str:
        return transcript

    async def fake_triage(_transcript: str, **kwargs) -> TriageDecision:
        nonlocal active_triage_calls, max_active_triage_calls
        triage_scopes.append(str(kwargs.get("scope")))
        active_triage_calls += 1
        max_active_triage_calls = max(max_active_triage_calls, active_triage_calls)
        await asyncio.sleep(0.01)
        active_triage_calls -= 1
        return TriageDecision(worth_storing=False, reason=f"{kwargs.get('scope')} skipped")

    async def fail_extract(_transcript: str, **_kwargs) -> list[InsightDraft]:
        raise AssertionError("extractor should not run when triage skips")

    monkeypatch.setattr("core.agents.orchestrator.scrub_pii_transcript", fake_scrub)
    monkeypatch.setattr("core.agents.orchestrator.run_triage_agent", fake_triage)
    monkeypatch.setattr("core.agents.orchestrator.extract_insights", fail_extract)

    normalized = normalize_ingestion_request(
        SessionIngestionRequest(
            source="cursor",
            session_id="session-concurrent",
            user_id="dev@example.com",
            user_email="dev@example.com",
            org_id="acme",
            transcript="Turn 1 [user]: Store this company fact.",
            metadata={"profile": {"company": "Acme"}},
        )
    )

    result = asyncio.run(
        run_extraction_pipeline(
            session_id="session-concurrent",
            user_id="dev@example.com",
            transcript=normalized.transcript,
            source=SourceType.CURSOR,
            neo4j_client=mock_neo4j,
            chroma_client=mock_chroma,
            contribute_to_global=True,
            normalized_session=normalized,
        )
    )

    assert result["insights_stored"] == 0
    assert set(triage_scopes) == {"user", "global"}
    assert max_active_triage_calls == 2


def test_user_pipeline_error_does_not_skip_global_pipeline(monkeypatch, mock_neo4j, mock_chroma) -> None:
    async def fake_scrub(transcript: str, **_kwargs) -> str:
        return transcript

    async def fake_triage(_transcript: str, **_kwargs) -> TriageDecision:
        return TriageDecision(worth_storing=True, reason="durable")

    async def fake_extract(_transcript: str, **kwargs) -> list[InsightDraft]:
        if kwargs.get("scope") == "user":
            raise RuntimeError("user extractor temporary failure")
        return [
            InsightDraft(
                what="company launch plan belongs in shared memory",
                why=None,
                how=None,
                outcome="exploratory",
                memory_kind="company_fact",
                tags=["gtm"],
                display_label="Shared launch plan",
                display_summary="The company launch plan should be retrievable as shared memory.",
            )
        ]

    monkeypatch.setattr("core.agents.orchestrator.scrub_pii_transcript", fake_scrub)
    monkeypatch.setattr("core.agents.orchestrator.run_triage_agent", fake_triage)
    monkeypatch.setattr("core.agents.orchestrator.extract_insights", fake_extract)

    normalized = normalize_ingestion_request(
        SessionIngestionRequest(
            source="cursor",
            session_id="session-user-error-global-ok",
            user_id="dev@example.com",
            user_email="dev@example.com",
            org_id="acme",
            transcript="Turn 1 [user]: Company launch plan is soft launch first.",
            metadata={"profile": {"company": "Acme"}},
        )
    )

    result = asyncio.run(
        run_extraction_pipeline(
            session_id="session-user-error-global-ok",
            user_id="dev@example.com",
            transcript=normalized.transcript,
            source=SourceType.CURSOR,
            neo4j_client=mock_neo4j,
            chroma_client=mock_chroma,
            contribute_to_global=True,
            normalized_session=normalized,
        )
    )

    assert result["insights_stored"] == 1
    assert result["user"]["skipped_reason"] == "insight extractor failed"
    assert result["global"]["insights_stored"] == 1
    assert any("Insight extractor failed" in error for error in result["errors"])
