from __future__ import annotations

import pytest

from core.graph_schema_v2 import (
    BelongsToEdge,
    Concept,
    ConceptCategory,
    ConversationType,
    HasProblemEdge,
    NodeType,
    Problem,
    ProblemExtractionOutput,
    ProblemSeverity,
    ProblemStatus,
    ProposedForEdge,
    RecursAsEdge,
    ResolvedByEdge,
    Session,
    SessionResolutionStatus,
    Solution,
    SolutionDraft,
    validate_edge,
    validate_node,
)


RAW_CONVERSATION = """
User: I'm getting a CORS error in my FastAPI app. The frontend
      is on localhost:3000 and backend on localhost:8000.
LLM:  You need to add CORSMiddleware. Here's how: [code snippet]
User: Still getting the error after adding it.
LLM:  Make sure the middleware is added before your router
      includes. Order matters in FastAPI.
User: That fixed it!
""".strip()


def test_schema_smoke_fastapi_cors_debugging_flow() -> None:
    fastapi = Concept(
        canonical_label="fastapi",
        category=ConceptCategory.FRAMEWORK,
        description="Python web framework used by the backend service.",
    )
    cors = Concept(
        canonical_label="cors",
        category=ConceptCategory.PROTOCOL,
        description="Cross-Origin Resource Sharing policy behavior.",
    )
    problem = Problem(
        canonical_label="fastapi cors middleware order",
        description="CORS policy continued failing until middleware ordering was fixed.",
        context_brief="fastapi backend on localhost:8000 with frontend at localhost:3000",
        concepts=["fastapi", "cors"],
        severity=ProblemSeverity.HIGH,
        status=ProblemStatus.RESOLVED,
        symptom_keywords=["cors", "middleware", "order"],
        first_seen_turn=1,
        last_seen_turn=5,
        root_cause_known=True,
    )
    solution = Solution(
        canonical_label="add corsmiddleware before router includes",
        description="add corsmiddleware before router includes",
        tried=True,
        worked=True,
        steps=[
            "Add CORSMiddleware declaration.",
            "Register middleware before including routers.",
            "Restart service and retry frontend call.",
        ],
    )
    unknown_outcome_solution = Solution(
        canonical_label="retry with relaxed origins",
        description="retry with relaxed origins",
        tried=True,
        worked=None,
    )
    session = Session(
        conversation_type=ConversationType.DEBUGGING,
        resolution_status=SessionResolutionStatus.RESOLVED,
        title="FastAPI CORS debugging session",
        summary=(
            "User reported persistent CORS failures; final fix was middleware order before router includes."
        ),
        message_count=6,
    )

    for node in [fastapi, cors, problem, solution, unknown_outcome_solution, session]:
        validate_node(node)

    # 8-word limit is gone — this should now pass.
    long_label_problem = Problem(
        canonical_label="fastapi cors middleware order after router include on staging backend api endpoint",
        description="Long but still valid lowercase label.",
        context_brief="long label validation path",
        concepts=["fastapi", "cors"],
    )
    validate_node(long_label_problem)

    extraction_output = ProblemExtractionOutput(
        canonical_label="fastapi cors middleware order",
        context_brief="fastapi backend on localhost:8000 with frontend at localhost:3000",
        concepts=["fastapi", "cors"],
        severity=ProblemSeverity.HIGH,
        status=ProblemStatus.RESOLVED,
        symptom_keywords=["cors", "middleware", "order"],
        solutions=[
            SolutionDraft(
                canonical_label="add corsmiddleware before router includes",
                description="add corsmiddleware before router includes",
                tried=True,
                worked=True,
            ),
            SolutionDraft(
                canonical_label="retry with relaxed origins",
                description="retry with relaxed origins",
                tried=True,
                worked=None,
            ),
        ],
    )

    # Explicitly verify None is distinct from False for the resolution loop contract.
    assert unknown_outcome_solution.worked is None
    assert unknown_outcome_solution.worked is not False
    assert extraction_output.solutions[1].worked is None
    assert extraction_output.solutions[1].worked is not False
    assert isinstance(extraction_output.solutions[0], SolutionDraft)
    assert extraction_output.canonical_label == "fastapi cors middleware order"

    edges = [
        (BelongsToEdge(from_node_type=NodeType.CONCEPT), cors, fastapi),
        (BelongsToEdge(from_node_type=NodeType.PROBLEM), problem, cors),
        (ProposedForEdge(), solution, problem),
        (ResolvedByEdge(), problem, solution),
        (HasProblemEdge(), session, problem),
    ]
    for edge, source_node, target_node in edges:
        validate_edge(edge, source_node, target_node)

    # RECURS_AS direction fix: Session -> Problem is valid.
    validate_edge(RecursAsEdge(recurrence_index=1), session, problem)
    # Old direction Problem -> Problem is now invalid.
    with pytest.raises(ValueError):
        validate_edge(RecursAsEdge(recurrence_index=2), problem, long_label_problem)

    # Whiteboard sanity checks for expected canonical labels.
    assert fastapi.canonical_label == "fastapi"
    assert cors.canonical_label == "cors"
    assert problem.canonical_label == "fastapi cors middleware order"

    # Keep the transcript in the test to ensure this is grounded in a real conversation.
    assert "That fixed it!" in RAW_CONVERSATION
