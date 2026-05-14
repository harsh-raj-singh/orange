from __future__ import annotations

from unittest.mock import Mock

from core.agents.concept_extractor import ConceptExtractionResult
from core.agents.debug_extractor import DebugExtractionResult, ResolutionStatus
from core.graph_schema_v2 import ProblemExtractionOutput, Session
from core.graph_upsert.writer import GraphUpsertEngine
from core.mcp_server.assembler import _render_context_block, _score_node


def _session(node_id: str = "session-1") -> Session:
    return Session(node_id=node_id, title="test session", summary="summary", message_count=4)


def _base_problem_output() -> ProblemExtractionOutput:
    return ProblemExtractionOutput(
        canonical_label="fastapi cors middleware order",
        context_brief="middleware applied after route registration causing options 403",
        concepts=["fastapi", "cors"],
    )


def _debug_result_for(problem_output: ProblemExtractionOutput) -> DebugExtractionResult:
    return DebugExtractionResult(problems=[problem_output], session_resolution_status=ResolutionStatus.OPEN)


def test_resolved_ranks_above_open() -> None:
    resolved = {"status": "resolved", "neighbors": [], "recurrence_count": 1}
    open_prob = {"status": "open", "neighbors": [], "recurrence_count": 1}
    assert _score_node(resolved) > _score_node(open_prob)


def test_worked_solution_boosts_score() -> None:
    without = {"status": "open", "neighbors": [], "recurrence_count": 0}
    with_solution = {
        "status": "open",
        "recurrence_count": 0,
        "neighbors": [{"rel_type": "RESOLVED_BY", "node_type": "Solution"}],
    }
    assert _score_node(with_solution) > _score_node(without)


def test_recurrence_boosts_score() -> None:
    low = {"status": "open", "neighbors": [], "recurrence_count": 1}
    high = {"status": "open", "neighbors": [], "recurrence_count": 5}
    assert _score_node(high) > _score_node(low)


def test_context_block_renders_solution_neighbor() -> None:
    node = {
        "canonical_label": "fastapi cors",
        "context_brief": "middleware order issue",
        "status": "resolved",
        "recurrence_count": 2,
        "node_type": "Problem",
        "neighbors": [
            {
                "rel_type": "RESOLVED_BY",
                "node_type": "Solution",
                "canonical_label": "move middleware before router",
                "context_brief": "fixes preflight",
                "status": "",
            },
            {
                "rel_type": "PROPOSED_FOR",
                "node_type": "Solution",
                "canonical_label": "add allow_origins wildcard",
                "context_brief": "broad origin config",
                "status": "",
            },
            {
                "rel_type": "PROPOSED_FOR",
                "node_type": "Solution",
                "canonical_label": "increase timeout",
                "context_brief": "unrelated tuning",
                "status": "failed",
            },
        ],
    }
    block = _render_context_block(node)
    assert "fastapi cors" in block
    assert "move middleware before router" in block
    assert "SOLUTION" in block
    assert "✓ worked" in block
    assert "✗ tried, did not work" in block
    assert "~ tried, outcome unknown" in block


def test_cross_session_solution_linked_to_new_problem(mock_neo4j, mock_chroma) -> None:
    mock_chroma.query_returns = [
        {"ids": [[]], "distances": [[]], "metadatas": [[]]},
        {
            "ids": [["sol-1"]],
            "distances": [[0.15]],  # similarity 0.85
            "metadatas": [[
                {
                    "node_type": "Solution",
                    "neo4j_node_id": "sol-1",
                    "canonical_label": "move middleware",
                    "context_brief": "fixes cors",
                    "parent_problem_id": "prob-old",
                    "user_id": "u1",
                }
            ]],
        },
    ]

    engine = GraphUpsertEngine(neo4j=mock_neo4j, chroma=mock_chroma, llm=None)
    engine.upsert(
        session=_session("session-2"),
        user_id="u1",
        debug_result=_debug_result_for(_base_problem_output()),
        concept_result=ConceptExtractionResult(concepts=[]),
    )

    assert any(edge[0] == "PROPOSED_FOR" and edge[1] == "sol-1" and edge[2] != "prob-old" for edge in mock_neo4j.edges)


def test_related_to_written_for_gray_zone_create(mock_neo4j, mock_chroma) -> None:
    mock_chroma.query_returns = [
        {
            "ids": [["prob-old"]],
            "distances": [[0.35]],  # similarity 0.65 gray zone
            "metadatas": [[{"canonical_label": "fastapi cors middleware issue", "context_brief": "related context"}]],
        },
        {"ids": [[]], "distances": [[]], "metadatas": [[]]},
    ]
    mock_llm = Mock(return_value='{"same_problem": false, "reasoning": "different root"}')

    engine = GraphUpsertEngine(neo4j=mock_neo4j, chroma=mock_chroma, llm=mock_llm)
    engine.upsert(
        session=_session("session-3"),
        user_id="u1",
        debug_result=_debug_result_for(_base_problem_output()),
        concept_result=ConceptExtractionResult(concepts=[]),
    )

    assert any(edge[0] == "RELATED_TO" for edge in mock_neo4j.edges)


def test_low_similarity_solution_not_linked(mock_neo4j, mock_chroma) -> None:
    mock_chroma.query_returns = [
        {"ids": [[]], "distances": [[]], "metadatas": [[]]},
        {
            "ids": [["sol-old"]],
            "distances": [[0.40]],  # similarity 0.60
            "metadatas": [[
                {
                    "node_type": "Solution",
                    "neo4j_node_id": "sol-old",
                    "canonical_label": "old solution",
                    "context_brief": "old description",
                    "parent_problem_id": "prob-old",
                    "user_id": "u1",
                }
            ]],
        },
    ]

    engine = GraphUpsertEngine(neo4j=mock_neo4j, chroma=mock_chroma, llm=None)
    engine.upsert(
        session=_session("session-4"),
        user_id="u1",
        debug_result=_debug_result_for(_base_problem_output()),
        concept_result=ConceptExtractionResult(concepts=[]),
    )

    cross_session_edges = [e for e in mock_neo4j.edges if e[0] == "PROPOSED_FOR" and e[1] == "sol-old"]
    assert len(cross_session_edges) == 0
