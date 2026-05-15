from __future__ import annotations

from core.agents.extraction_outputs import EnrichedProblem, ExtractedSolution, IssueAgentOutput, SolutionAgentOutput
from core.graph_schema_v2 import ConfidenceLevel, Session, SolutionOutcome, SourceType
from core.graph_upsert.writer import GraphUpsertEngine


def test_upsert_v2_merges_session_before_edges_and_preserves_source(mock_neo4j, mock_chroma) -> None:
    session = Session(
        node_id="session-v2",
        source=SourceType.CURSOR,
        title="v2",
        summary="summary",
        message_count=2,
        external_session_id="cursor-thread-1",
        org_id="org_1",
        participants=["dev_1", "assistant"],
        client_name="cursor",
        client_version="1.0",
        source_url="cursor://thread/1",
    )
    issue_output = IssueAgentOutput(
        session_id="session-v2",
        problems=[
            EnrichedProblem(
                segment_id="p1",
                canonical_label="fastapi cors middleware order",
                description="CORS preflight fails because middleware is registered after routes.",
                llm_reasoning="The transcript centers on one runtime middleware ordering issue.",
                first_seen_turn=1,
                last_seen_turn=2,
                turn_sequence=[1, 2],
                tech_stack=["FastAPI"],
            )
        ],
    )
    solution_output = SolutionAgentOutput(
        session_id="session-v2",
        solutions=[
            ExtractedSolution(
                canonical_label="move cors middleware before route registration",
                description="Register CORSMiddleware before include_router.",
                in_depth_summary="Move CORSMiddleware setup above route registration so OPTIONS requests hit middleware.",
                outcome=SolutionOutcome.SUCCESS,
                addresses_problem_label="fastapi cors middleware order",
                confidence=ConfidenceLevel.HIGH,
                attempt_number=1,
                applied_turn=3,
                turn_sequence=[3],
            )
        ],
    )

    engine = GraphUpsertEngine(neo4j=mock_neo4j, chroma=mock_chroma, llm=None)
    summary = engine.upsert_v2(
        session=session,
        user_id="u1",
        issue_output=issue_output,
        solution_output=solution_output,
    )

    first_session_merge = next(i for i, (query, _) in enumerate(mock_neo4j.query_log) if "H4:MERGE_SESSION" in query)
    first_direct_edge = next(i for i, (query, _) in enumerate(mock_neo4j.query_log) if "MERGE (a)-[r:" in query)

    assert summary.sessions_written == 1
    assert summary.problems_created == 1
    assert summary.solutions_written == 1
    assert first_session_merge < first_direct_edge
    assert mock_neo4j.sessions[("session-v2", "u1")]["source"] == "cursor"
    assert mock_neo4j.sessions[("session-v2", "u1")]["participants"] == ["dev_1", "assistant"]
    assert {upsert["metadatas"][0]["source"] for upsert in mock_chroma.upserts} == {"cursor"}


def test_upsert_v2_chroma_documents_point_to_neo4j_node_ids(mock_neo4j, mock_chroma) -> None:
    session = Session(node_id="session-v2", source=SourceType.CLAUDE)
    issue_output = IssueAgentOutput(
        session_id="session-v2",
        problems=[
            EnrichedProblem(
                segment_id="p1",
                canonical_label="module import failure",
                description="Python import fails after package layout change.",
                llm_reasoning="The transcript identifies one import failure.",
            )
        ],
    )
    solution_output = SolutionAgentOutput(session_id="session-v2", solutions=[])

    GraphUpsertEngine(neo4j=mock_neo4j, chroma=mock_chroma, llm=None).upsert_v2(
        session=session,
        user_id="u1",
        issue_output=issue_output,
        solution_output=solution_output,
    )

    problem_upsert = next(item for item in mock_chroma.upserts if item["metadatas"][0]["node_type"] == "Problem")
    metadata = problem_upsert["metadatas"][0]

    assert problem_upsert["ids"][0].startswith("problem_")
    assert metadata["neo4j_node_id"].startswith("problem_")
    assert metadata["source"] == "claude"
