from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from core.agents.concept_extractor import ConceptDraft, ConceptExtractionResult
from core.agents.debug_extractor import DebugExtractionResult, ResolutionStatus
from core.agents.runner import ExtractionResult
from core.graph_schema_v2 import (
    ConceptCategory,
    ProblemExtractionOutput,
    ProblemSeverity,
    ProblemStatus,
    SolutionDraft,
    SourceType,
)
from core.mcp_server.handlers import (
    _STORE_SESSION_CACHE,
    handle_ping_context,
    handle_resolve_problem,
    handle_store_session,
)
from core.mcp_server.models import (
    PingContextRequest,
    ResolveProblemRequest,
    StoreSessionRequest,
)
from core.source_registry import ConversationType


@pytest.fixture(autouse=True)
def clear_store_session_cache() -> None:
    _STORE_SESSION_CACHE.clear()


def test_ping_context_returns_context_blocks(mock_neo4j, mock_chroma) -> None:
    mock_neo4j.problems[("p1", "u1")] = {
        "node_id": "p1",
        "canonical_label": "fastapi cors middleware order",
        "context_brief": "middleware applied after route registration causing options 403",
        "status": "resolved",
    }
    mock_neo4j.problems[("p2", "u1")] = {
        "node_id": "p2",
        "canonical_label": "redis connection pool exhaustion",
        "context_brief": "pool hitting max connections under load",
        "status": "open",
    }
    mock_neo4j.solutions[("move corsmiddleware before include_router", "p1", "u1")] = {
        "node_id": "s1",
        "canonical_label": "move corsmiddleware before include_router",
        "description": "move corsmiddleware before include_router",
        "worked": True,
    }
    mock_neo4j.edges.add(("RESOLVED_BY", "p1", "s1", "u1"))

    mock_chroma.query_returns = {
        "ids": [["p1", "p2"]],
        "distances": [[0.11, 0.22]],
        "metadatas": [[
            {"user_id": "u1", "node_type": "Problem", "canonical_label": "fastapi cors middleware order"},
            {"user_id": "u1", "node_type": "Problem", "canonical_label": "redis connection pool exhaustion"},
        ]],
    }

    req = PingContextRequest(query="cors problem", user_id="u1", source="cursor")
    resp = asyncio.run(handle_ping_context(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert len(resp.matched_nodes) > 0
    assert any(n.node_type == "Problem" for n in resp.matched_nodes)
    assert resp.matched_nodes[0].node_data.get("canonical_label") is not None
    assert len(resp.node_ids_used) > 0


def test_ping_context_respects_token_budget(mock_neo4j, mock_chroma) -> None:
    ids: list[str] = []
    metadatas: list[dict] = []
    for idx in range(10):
        node_id = f"p{idx}"
        ids.append(node_id)
        metadatas.append({"user_id": "u1", "node_type": "Problem", "canonical_label": f"problem {idx}"})
        mock_neo4j.problems[(node_id, "u1")] = {
            "node_id": node_id,
            "canonical_label": f"problem {idx}",
            "context_brief": "x" * 2000,
            "status": "open",
        }

    mock_chroma.query_returns = {
        "ids": [ids],
        "distances": [[0.2] * 10],
        "metadatas": [metadatas],
    }

    req = PingContextRequest(query="anything", user_id="u1", source="cursor")
    resp = asyncio.run(handle_ping_context(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert len(resp.matched_nodes) > 0
    assert any(n.node_type == "Problem" for n in resp.matched_nodes)
    assert resp.matched_nodes[0].node_data.get("canonical_label") is not None
    assert len(resp.node_ids_used) > 0


def test_ping_context_invalid_source_raises(mock_neo4j, mock_chroma) -> None:
    req = PingContextRequest(query="x", user_id="u1", source="nonexistent_tool")
    with pytest.raises(ValueError, match="source"):
        asyncio.run(handle_ping_context(req, neo4j=mock_neo4j, chroma=mock_chroma))


def test_store_session_returns_summary(monkeypatch: pytest.MonkeyPatch, mock_neo4j, mock_chroma) -> None:
    async def fake_run_extraction(session_id: str, transcript: str, source: SourceType) -> ExtractionResult:
        debug_result = DebugExtractionResult(
            problems=[
                ProblemExtractionOutput(
                    canonical_label="fastapi cors middleware order",
                    context_brief="middleware after route include",
                    concepts=["cors", "fastapi"],
                    severity=ProblemSeverity.HIGH,
                    status=ProblemStatus.RESOLVED,
                    solutions=[
                        SolutionDraft(
                            canonical_label="move corsmiddleware before include_router",
                            description="move corsmiddleware before include_router",
                            tried=True,
                            worked=True,
                        )
                    ],
                )
            ],
            session_resolution_status=ResolutionStatus.RESOLVED,
        )
        concept_result = ConceptExtractionResult(
            concepts=[
                ConceptDraft(
                    canonical_label="fastapi",
                    category=ConceptCategory.FRAMEWORK,
                    parent_concept=None,
                )
            ]
        )
        return ExtractionResult(
            session_id=session_id,
            source=source,
            conversation_type=ConversationType.DEBUGGING,
            classifier_confidence=0.92,
            debug_result=debug_result,
            brainstorm_result=None,
            concept_result=concept_result,
            extraction_timestamp=datetime.now(timezone.utc),
        )

    monkeypatch.setattr("core.mcp_server.handlers.run_extraction", fake_run_extraction)

    req = StoreSessionRequest(
        transcript="we had a cors problem and fixed it by moving middleware",
        source="cursor",
        user_id="u1",
        session_id="sess-abc",
    )
    resp = asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))

    assert resp.session_id == "sess-abc"
    assert isinstance(resp.problems_created, int)
    assert isinstance(resp.problems_merged, int)


def test_store_session_idempotent(monkeypatch: pytest.MonkeyPatch, mock_neo4j, mock_chroma) -> None:
    calls = {"count": 0}

    async def fake_run_extraction(session_id: str, transcript: str, source: SourceType) -> ExtractionResult:
        calls["count"] += 1
        debug_result = DebugExtractionResult(
            problems=[
                ProblemExtractionOutput(
                    canonical_label="fastapi cors middleware order",
                    context_brief="middleware after route include",
                    concepts=["cors", "fastapi"],
                    severity=ProblemSeverity.HIGH,
                    status=ProblemStatus.RESOLVED,
                )
            ],
            session_resolution_status=ResolutionStatus.RESOLVED,
        )
        return ExtractionResult(
            session_id=session_id,
            source=source,
            conversation_type=ConversationType.DEBUGGING,
            classifier_confidence=0.8,
            debug_result=debug_result,
            brainstorm_result=None,
            concept_result=ConceptExtractionResult(concepts=[]),
            extraction_timestamp=datetime.now(timezone.utc),
        )

    monkeypatch.setattr("core.mcp_server.handlers.run_extraction", fake_run_extraction)

    req = StoreSessionRequest(transcript="...", source="cursor", user_id="u1", session_id="sess-xyz")
    resp1 = asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))
    resp2 = asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))

    assert resp1.problems_created == resp2.problems_created
    assert calls["count"] == 1


def test_store_session_rejects_empty_transcript(mock_neo4j, mock_chroma) -> None:
    req = StoreSessionRequest(transcript="", source="cursor", user_id="u1", session_id="s1")
    with pytest.raises(ValueError, match="transcript"):
        asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))


def test_resolve_problem_writes_edge(mock_neo4j, mock_chroma) -> None:
    mock_neo4j.problems[("p1", "u1")] = {
        "node_id": "p1",
        "canonical_label": "fastapi cors middleware order",
        "context_brief": "middleware after router include",
        "status": "open",
    }

    req = ResolveProblemRequest(
        session_id="sess-1",
        user_id="u1",
        problem_label="fastapi cors middleware order",
        solution_that_worked="move CORSMiddleware before include_router",
    )
    resp = asyncio.run(handle_resolve_problem(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert resp.resolved is True
    assert resp.problem_node_id is not None
    assert ("RESOLVED_BY", resp.problem_node_id, resp.solution_node_id, "u1") in mock_neo4j.edges


def test_resolve_problem_unknown_label(mock_neo4j, mock_chroma) -> None:
    req = ResolveProblemRequest(
        session_id="s1",
        user_id="u1",
        problem_label="nonexistent problem",
        solution_that_worked="anything",
    )
    resp = asyncio.run(handle_resolve_problem(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert resp.resolved is False
    assert resp.problem_node_id is None
