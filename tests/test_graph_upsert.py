from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from unittest.mock import Mock

import pytest

from core.agents.concept_extractor import ConceptExtractionResult
from core.agents.debug_extractor import DebugExtractionResult, ResolutionStatus
from core.graph_schema_v2 import (
    ConfidenceLevel,
    EdgeType,
    Problem,
    ProblemExtractionOutput,
    Session,
    SolutionDraft,
)
from core.graph_upsert.dedup import run_dedup
from core.graph_upsert.embeddings import build_problem_embed_string
from core.graph_upsert.writer import GraphUpsertEngine


@dataclass
class FakeResult:
    record: dict[str, Any] | None = None

    def single(self) -> dict[str, Any] | None:
        return self.record


class FakeNeo4j:
    def __init__(self) -> None:
        self.sessions: dict[tuple[str, str], dict[str, Any]] = {}
        self.concepts: dict[tuple[str, str], dict[str, Any]] = {}
        self.problems: dict[tuple[str, str], dict[str, Any]] = {}
        self.solutions: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.edges: set[tuple[str, str, str, str]] = set()
        self.query_log: list[tuple[str, dict[str, Any]]] = []
        self.problem_create_calls = 0

    def run(self, query: str, **params: Any) -> FakeResult:
        self.query_log.append((query, params))

        if "H4:CHECK_CONTENT_HASH_PROBLEM" in query:
            for (node_id, uid), payload in self.problems.items():
                if uid == params["user_id"] and payload.get("content_hash") == params["content_hash"]:
                    return FakeResult({"node_id": node_id})
            return FakeResult(None)

        if "H4:CHECK_CONTENT_HASH_SOLUTION" in query:
            for (_, _, uid), payload in self.solutions.items():
                if uid == params["user_id"] and payload.get("content_hash") == params["content_hash"]:
                    return FakeResult({"node_id": payload["node_id"]})
            return FakeResult(None)

        if "H4:MERGE_SESSION" in query:
            key = (params["node_id"], params["user_id"])
            self.sessions[key] = dict(params)
            return FakeResult({"node_id": params["node_id"]})

        if "H4:MERGE_CONCEPT" in query:
            key = (params["canonical_label"], params["user_id"])
            existing = self.concepts.get(key, {})
            node_id = existing.get("node_id", params["node_id"])
            payload = dict(params)
            payload["node_id"] = node_id
            self.concepts[key] = payload
            return FakeResult({"node_id": node_id})

        if "H4:CREATE_PROBLEM" in query:
            self.problem_create_calls += 1
            key = (params["node_id"], params["user_id"])
            payload = dict(params)
            self.problems[key] = payload
            return FakeResult({"node_id": params["node_id"]})

        if "H4:INCREMENT_RECURRENCE" in query:
            key = (params["problem_id"], params["user_id"])
            payload = self.problems.get(key)
            if payload:
                payload["recurrence_count"] = int(payload.get("recurrence_count", 0)) + 1
            return FakeResult(None)

        if "H4:MERGE_SOLUTION" in query:
            key = (params["canonical_label"], params["parent_problem_id"], params["user_id"])
            existing = self.solutions.get(key, {})
            node_id = existing.get("node_id", params["node_id"])
            payload = dict(params)
            payload["node_id"] = node_id
            self.solutions[key] = payload
            return FakeResult({"node_id": node_id})

        marker_match = re.search(r"H4:EDGE_([A-Z_]+)", query)
        if marker_match:
            marker = marker_match.group(1)
            edge_type = {
                "CONCEPT_BELONGS_TO": "BELONGS_TO",
                "PROBLEM_BELONGS_TO": "BELONGS_TO",
                "HAS_PROBLEM": "HAS_PROBLEM",
                "RECURS_AS": "RECURS_AS",
                "PROPOSED_FOR": "PROPOSED_FOR",
                "RESOLVED_BY": "RESOLVED_BY",
            }[marker]
            src = (
                params.get("session_id")
                or params.get("child_id")
                or params.get("problem_id")
                or params.get("solution_id")
            )
            dst = params.get("problem_id") or params.get("parent_id") or params.get("concept_id") or params.get("solution_id")

            if marker == "PROPOSED_FOR":
                src = params.get("solution_id")
                dst = params.get("problem_id")
            if marker == "RESOLVED_BY":
                src = params.get("problem_id")
                dst = params.get("solution_id")
            if marker == "HAS_PROBLEM":
                src = params.get("session_id")
                dst = params.get("problem_id")
            if marker == "RECURS_AS":
                src = params.get("session_id")
                dst = params.get("problem_id")
            if marker == "CONCEPT_BELONGS_TO":
                src = params.get("child_id")
                dst = params.get("parent_id")
            if marker == "PROBLEM_BELONGS_TO":
                src = params.get("problem_id")
                dst = params.get("concept_id")

            self.edges.add((edge_type, str(src), str(dst), params["user_id"]))
            return FakeResult(None)

        return FakeResult(None)


class FakeChroma:
    def __init__(self, query_returns: Any | None = None) -> None:
        self.query_returns = query_returns if query_returns is not None else {"ids": [[]], "distances": [[]], "metadatas": [[]]}
        self.query_calls: list[dict[str, Any]] = []
        self.upserts: list[dict[str, Any]] = []

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.query_calls.append(kwargs)
        if isinstance(self.query_returns, list):
            if self.query_returns:
                return self.query_returns.pop(0)
            return {"ids": [[]], "distances": [[]], "metadatas": [[]]}
        return self.query_returns

    def upsert(self, **kwargs: Any) -> None:
        self.upserts.append(kwargs)


def _debug_result_for(problem_output: ProblemExtractionOutput) -> DebugExtractionResult:
    return DebugExtractionResult(problems=[problem_output], session_resolution_status=ResolutionStatus.OPEN)


def _base_problem_output(solutions: list[SolutionDraft] | None = None) -> ProblemExtractionOutput:
    return ProblemExtractionOutput(
        canonical_label="fastapi cors middleware order",
        context_brief="middleware applied after router include causing preflight failure",
        concepts=["fastapi", "cors"],
        symptom_keywords=["cors", "middleware", "order"],
        solutions=solutions or [],
    )


def _session() -> Session:
    return Session(node_id="session-1", title="debug session", summary="summary", message_count=6)


def _problem_upsert_count(chroma: FakeChroma) -> int:
    return sum(1 for item in chroma.upserts if item["metadatas"][0].get("node_type") == "Problem")


def test_embed_strings_include_context() -> None:
    problem = Problem(canonical_label="fastapi cors", context_brief="middleware order issue")
    s = build_problem_embed_string(problem)
    assert "fastapi cors" in s
    assert "middleware order issue" in s
    assert len(s) > len(problem.canonical_label)


def test_high_similarity_merges_without_llm() -> None:
    sample_problem = Problem(
        canonical_label="fastapi cors middleware order",
        context_brief="middleware after route include",
    )
    mock_chroma = Mock()
    mock_chroma.query.return_value = {
        "distances": [[0.08]],
        "ids": [["existing-id-123"]],
        "metadatas": [[{"context_brief": "same problem", "canonical_label": "fastapi cors middleware order"}]],
    }

    decision = run_dedup(problem=sample_problem, user_id="u1", chroma=mock_chroma, llm=None)

    assert decision.action == "MERGE"
    assert decision.existing_node_id == "existing-id-123"
    assert decision.arbitration_used is False


def test_low_similarity_creates_new() -> None:
    sample_problem = Problem(
        canonical_label="fastapi cors middleware order",
        context_brief="middleware after route include",
    )
    mock_chroma = Mock()
    mock_chroma.query.return_value = {
        "distances": [[0.70]],
        "ids": [["far-node"]],
        "metadatas": [[{"context_brief": "unrelated context", "canonical_label": "other label"}]],
    }

    decision = run_dedup(problem=sample_problem, user_id="u1", chroma=mock_chroma, llm=None)

    assert decision.action == "CREATE"
    assert decision.arbitration_used is False


def test_gray_zone_triggers_llm() -> None:
    sample_problem = Problem(
        canonical_label="fastapi cors middleware order",
        context_brief="middleware after route include",
    )
    mock_chroma = Mock()
    mock_chroma.query.return_value = {
        "distances": [[0.35]],
        "ids": [["candidate-1"]],
        "metadatas": [[{"context_brief": "same root cause", "canonical_label": "fastapi cors middleware order"}]],
    }
    mock_llm = Mock(return_value='{"same_problem": true, "reasoning": "same root cause"}')

    decision = run_dedup(problem=sample_problem, user_id="u1", chroma=mock_chroma, llm=mock_llm)

    assert decision.action == "MERGE"
    assert decision.arbitration_used is True
    assert mock_llm.call_count == 1


def test_where_filter_failure_falls_back_without_crashing() -> None:
    sample_problem = Problem(
        canonical_label="fastapi cors middleware order",
        context_brief="middleware after route include",
    )
    mock_collection = Mock()
    mock_collection.query.side_effect = [
        RuntimeError("where filter failed: missing metadata key"),
        {
            "distances": [[0.19, 0.75]],
            "ids": [["existing-id-123", "other-user-id"]],
            "metadatas": [[
                {"node_type": "Problem", "user_id": "u1", "canonical_label": "fastapi cors middleware order", "context_brief": "same"},
                {"node_type": "Problem", "user_id": "u2", "canonical_label": "other", "context_brief": "other"},
            ]],
        },
    ]

    decision = run_dedup(problem=sample_problem, user_id="u1", chroma=mock_collection, llm=None)

    assert decision.action == "MERGE"
    assert decision.existing_node_id == "existing-id-123"
    assert mock_collection.query.call_count == 2


def test_merge_path_increments_recurrence(mock_neo4j: FakeNeo4j, mock_chroma: FakeChroma) -> None:
    mock_neo4j.problems[("existing-problem-1", "u1")] = {
        "node_id": "existing-problem-1",
        "user_id": "u1",
        "canonical_label": "fastapi cors middleware order",
        "context_brief": "middleware after router include",
        "recurrence_count": 1,
        "content_hash": "older-session-hash",
    }
    mock_chroma.query_returns = {
        "distances": [[0.05]],
        "ids": [["existing-problem-1"]],
        "metadatas": [[{"canonical_label": "fastapi cors middleware order", "context_brief": "same"}]],
    }

    engine = GraphUpsertEngine(neo4j=mock_neo4j, chroma=mock_chroma, llm=None)
    engine.upsert(
        session=_session(),
        user_id="u1",
        debug_result=_debug_result_for(_base_problem_output()),
        concept_result=ConceptExtractionResult(concepts=[]),
    )

    assert mock_neo4j.problems[("existing-problem-1", "u1")]["recurrence_count"] == 2
    assert ("RECURS_AS", "session-1", "existing-problem-1", "u1") in mock_neo4j.edges
    assert mock_neo4j.problem_create_calls == 0
    assert _problem_upsert_count(mock_chroma) == 0


def test_create_path_writes_to_neo4j_and_chroma(mock_neo4j: FakeNeo4j, mock_chroma: FakeChroma) -> None:
    mock_chroma.query_returns = {"distances": [[]], "ids": [[]], "metadatas": [[]]}

    engine = GraphUpsertEngine(neo4j=mock_neo4j, chroma=mock_chroma, llm=None)
    engine.upsert(
        session=_session(),
        user_id="u1",
        debug_result=_debug_result_for(_base_problem_output()),
        concept_result=ConceptExtractionResult(concepts=[]),
    )

    assert mock_neo4j.problem_create_calls == 1
    assert _problem_upsert_count(mock_chroma) == 1
    assert any(
        item["documents"][0] == "fastapi cors middleware order - middleware applied after router include causing preflight failure"
        for item in mock_chroma.upserts
        if item["metadatas"][0].get("node_type") == "Problem"
    )
    assert any(edge[0] == "HAS_PROBLEM" and edge[1] == "session-1" for edge in mock_neo4j.edges)


def test_idempotent_rerun(mock_neo4j: FakeNeo4j, mock_chroma: FakeChroma) -> None:
    mock_chroma.query_returns = {"distances": [[]], "ids": [[]], "metadatas": [[]]}

    engine = GraphUpsertEngine(neo4j=mock_neo4j, chroma=mock_chroma, llm=None)
    session = _session()
    debug = _debug_result_for(_base_problem_output())

    engine.upsert(session=session, user_id="u1", debug_result=debug, concept_result=ConceptExtractionResult(concepts=[]))
    engine.upsert(session=session, user_id="u1", debug_result=debug, concept_result=ConceptExtractionResult(concepts=[]))

    assert mock_neo4j.problem_create_calls == 1
    assert _problem_upsert_count(mock_chroma) == 1


def test_invalid_edge_skips_but_continues(monkeypatch: pytest.MonkeyPatch, mock_neo4j: FakeNeo4j, mock_chroma: FakeChroma) -> None:
    import core.graph_upsert.writer as writer_module

    mock_neo4j.problems[("existing-problem-2", "u1")] = {
        "node_id": "existing-problem-2",
        "user_id": "u1",
        "canonical_label": "fastapi cors middleware order",
        "context_brief": "middleware ordering",
        "recurrence_count": 1,
        "content_hash": "from-another-session",
    }
    mock_chroma.query_returns = {
        "distances": [[0.04]],
        "ids": [["existing-problem-2"]],
        "metadatas": [[{"canonical_label": "fastapi cors middleware order", "context_brief": "same"}]],
    }

    original_validate_edge = writer_module.validate_edge

    def patched_validate(edge: Any, source_node: Any, target_node: Any) -> None:
        if getattr(edge, "edge_type", None) == EdgeType.RECURS_AS:
            raise ValueError("forced invalid edge")
        original_validate_edge(edge, source_node, target_node)

    monkeypatch.setattr(writer_module, "validate_edge", patched_validate)

    solution = SolutionDraft(
        canonical_label="move corsmiddleware before router",
        description="move corsmiddleware before router",
        tried=True,
        worked=True,
        confidence=ConfidenceLevel.HIGH,
    )
    debug = _debug_result_for(_base_problem_output(solutions=[solution]))

    engine = GraphUpsertEngine(neo4j=mock_neo4j, chroma=mock_chroma, llm=None)
    summary = engine.upsert(
        session=_session(),
        user_id="u1",
        debug_result=debug,
        concept_result=ConceptExtractionResult(concepts=[]),
    )

    assert not any(edge[0] == "RECURS_AS" for edge in mock_neo4j.edges)
    assert any(edge[0] == "PROPOSED_FOR" for edge in mock_neo4j.edges)
    assert summary.edges_skipped >= 1


def test_worked_solution_writes_resolved_by(mock_neo4j: FakeNeo4j, mock_chroma: FakeChroma) -> None:
    mock_chroma.query_returns = {"distances": [[]], "ids": [[]], "metadatas": [[]]}

    solution_draft = SolutionDraft(
        canonical_label="fix x",
        description="do y",
        tried=True,
        worked=True,
        confidence=ConfidenceLevel.HIGH,
    )

    debug = _debug_result_for(_base_problem_output(solutions=[solution_draft]))

    engine = GraphUpsertEngine(neo4j=mock_neo4j, chroma=mock_chroma, llm=None)
    engine.upsert(
        session=_session(),
        user_id="u1",
        debug_result=debug,
        concept_result=ConceptExtractionResult(concepts=[]),
    )

    assert any(edge[0] == "RESOLVED_BY" for edge in mock_neo4j.edges)


@pytest.fixture
def mock_neo4j() -> FakeNeo4j:
    return FakeNeo4j()


@pytest.fixture
def mock_chroma() -> FakeChroma:
    return FakeChroma()
