"""
Entry point for post-chat extraction pipeline.
Called when user marks a chat as complete.

Execution order:
1. Solution Agent runs first (Issue Agent needs its output for context stitching)
2. Issue Agent runs with solution output injected
3. upsert_v2 writes everything to Neo4j
"""
import logging
from typing import Any

from core.agents.issue_agent.runner import run_issue_agent
from core.agents.solution_agent.runner import run_solution_agent
from core.graph_upsert.writer import GraphUpsertEngine
from core.graph_schema_v2 import Session, SourceType

logger = logging.getLogger(__name__)


async def run_extraction_pipeline(
    *,
    session_id: str,
    user_id: str,
    transcript: str,
    neo4j_client: Any,
    chroma_client: Any,
) -> dict:
    """
    Main pipeline. Call this when a chat is marked complete.

    Args:
        session_id:      The chat_id from chat_sessions table
        user_id:         The user who owns this session
        transcript:      Full conversation text, formatted as 'Turn N [role]: message'
        neo4j_client:    Neo4j driver instance
        chroma_client:   Chroma client instance

    Returns:
        dict with keys: problems_created, solutions_written, edges_written, errors
    """

    errors = []

    # Step 1 - Solution Agent
    solution_output = await run_solution_agent(session_id, transcript)

    # Step 2 - Issue Agent (needs solution_output for context stitching)
    try:
        issue_output = await run_issue_agent(
            session_id=session_id,
            transcript=transcript,
            solution_output=solution_output,
        )
    except Exception as exc:
        logger.error("issue_agent_failed", extra={"session_id": session_id, "error": str(exc)})
        errors.append(f"Issue agent failed: {exc}")
        return {"problems_created": 0, "solutions_written": 0, "edges_written": 0, "errors": errors}

    # Step 3 - Build Session node (fetch or create)
    session = Session(
        node_id=f"session_{session_id}",
        source=SourceType.STREAMLIT,
    )

    # Step 4 - Write to Neo4j
    try:
        engine = GraphUpsertEngine(neo4j=neo4j_client, chroma=chroma_client)
        summary = engine.upsert_v2(
            session=session,
            user_id=user_id,
            issue_output=issue_output,
            solution_output=solution_output,
        )
    except Exception as exc:
        logger.error("upsert_v2_failed", extra={"session_id": session_id, "error": str(exc)})
        errors.append(f"Writer failed: {exc}")
        return {"problems_created": 0, "solutions_written": 0, "edges_written": 0, "errors": errors}

    return {
        "problems_created": summary.problems_created,
        "solutions_written": summary.solutions_written,
        "edges_written": summary.edges_written,
        "errors": errors,
    }
