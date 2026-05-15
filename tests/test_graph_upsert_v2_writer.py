from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.agents.extraction_outputs import EnrichedProblem, ExtractedSolution, IssueAgentOutput, SolutionAgentOutput
from core.graph_schema_v2 import ConfidenceLevel, Session, SolutionOutcome, SourceType
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
            self.sessions[(params["node_id"], params["user_id"])] = dict(params)
            return FakeResult({"node_id": params["node_id"]})
        return FakeResult(None)


class FakeChroma:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []

    def upsert(self, **kwargs: Any) -> None:
        self.upserts.append(kwargs)


def test_upsert_v2_merges_session_before_edges_and_preserves_source() -> None:
    neo4j = FakeNeo4j()
    chroma = FakeChroma()
    session = Session(node_id="session-v2", source=SourceType.CURSOR, title="v2", summary="summary", message_count=2)
    issue_output = IssueAgentOutput(
        session_id="session-v2",
        problems=[
            EnrichedProblem(
                segment_id="p1",
                canonical_label="v2 problem",
                description="problem details",
                llm_reasoning="reasoning",
                first_seen_turn=1,
                last_seen_turn=1,
            )
        ],
    )
    solution_output = SolutionAgentOutput(
        session_id="session-v2",
        solutions=[
            ExtractedSolution(
                canonical_label="v2 solution",
                description="solution details",
                in_depth_summary="solution details",
                outcome=SolutionOutcome.SUCCESS,
                addresses_problem_label="v2 problem",
                confidence=ConfidenceLevel.HIGH,
            )
        ],
    )

    summary = GraphUpsertEngine(neo4j=neo4j, chroma=chroma, llm=None).upsert_v2(
        session=session,
        user_id="u1",
        issue_output=issue_output,
        solution_output=solution_output,
    )

    first_session_merge = next(i for i, (query, _) in enumerate(neo4j.query_log) if "H4:MERGE_SESSION" in query)
    first_direct_edge = next(i for i, (query, _) in enumerate(neo4j.query_log) if "MERGE (a)-[r:" in query)

    assert summary.sessions_written == 1
    assert first_session_merge < first_direct_edge
    assert neo4j.sessions[("session-v2", "u1")]["source"] == "cursor"
    assert any(params.get("canonical_label") == "v2 problem" and params.get("source") == "cursor" for _, params in neo4j.query_log)
    assert {upsert["metadatas"][0]["source"] for upsert in chroma.upserts} == {"cursor"}
