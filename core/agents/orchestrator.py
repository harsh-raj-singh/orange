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

from core.agents.issue_agent.prompts import ISSUE_AGENT_GLOBAL_SCOPE_PROMPT, ISSUE_AGENT_USER_SCOPE_PROMPT
from core.agents.issue_agent.runner import run_issue_agent
from core.agents.pii_scrubber import scrub_pii_transcript
from core.agents.prompt_scope import scoped_extraction_prompt
from core.agents.solution_agent.prompts import (
    SOLUTION_AGENT_GLOBAL_SCOPE_PROMPT,
    SOLUTION_AGENT_USER_SCOPE_PROMPT,
)
from core.agents.solution_agent.runner import run_solution_agent
from core.ingestion import NormalizedSession, SessionIngestionRequest, normalize_ingestion_request
from core.graph_upsert.writer import GraphUpsertEngine
from core.graph_schema_v2 import Session, SourceType

logger = logging.getLogger(__name__)


def _select_scope_prompts(scope: str) -> tuple[str, str]:
    if scope == "global":
        return SOLUTION_AGENT_GLOBAL_SCOPE_PROMPT, ISSUE_AGENT_GLOBAL_SCOPE_PROMPT
    return SOLUTION_AGENT_USER_SCOPE_PROMPT, ISSUE_AGENT_USER_SCOPE_PROMPT


def _session_node_from_normalized(scoped_session: NormalizedSession, summary: str) -> Session:
    return Session(
        node_id=scoped_session.session_node_id,
        source=scoped_session.source,
        started_at=scoped_session.started_at,
        ended_at=scoped_session.ended_at,
        message_count=scoped_session.message_count,
        title=scoped_session.title,
        summary=summary[:500],
        external_session_id=scoped_session.external_session_id,
        org_id=scoped_session.org_id,
        participants=scoped_session.participant_ids,
        client_name=scoped_session.client_name,
        client_version=scoped_session.client_version,
        source_url=scoped_session.source_url,
        ingested_at=scoped_session.ingested_at,
    )


def _global_session_from(normalized: NormalizedSession, scrubbed_transcript: str) -> NormalizedSession:
    return NormalizedSession(
        source=normalized.source,
        session_id=f"{normalized.session_id}_global",
        external_session_id=normalized.external_session_id,
        user_id="global",
        user_email=None,
        org_id=normalized.org_id,
        started_at=normalized.started_at,
        ended_at=normalized.ended_at,
        participants=[],
        client_metadata=normalized.client_metadata,
        tool_metadata=normalized.tool_metadata,
        raw_transcript=scrubbed_transcript,
        raw_messages=[],
        turns=[],
        metadata={**normalized.metadata, "scope": "global"},
        ingested_at=normalized.ingested_at,
    )


async def _run_for_scope(
    *,
    scoped_session: NormalizedSession,
    scoped_transcript: str,
    scoped_user_id: str,
    scope: str,
    neo4j_client: Any,
    chroma_client: Any,
    user_email: str | None = None,
    contributed_by: str | None = None,
) -> tuple[dict[str, int], list[str]]:
    scoped_errors: list[str] = []
    scoped_session_id = scoped_session.session_id
    solution_prompt, issue_prompt = _select_scope_prompts(scope)

    with scoped_extraction_prompt(solution_prompt):
        solution_output = await run_solution_agent(scoped_session_id, scoped_transcript)

    try:
        with scoped_extraction_prompt(issue_prompt):
            issue_output = await run_issue_agent(
                session_id=scoped_session_id,
                transcript=scoped_transcript,
                solution_output=solution_output,
            )
    except Exception as exc:
        logger.error("issue_agent_failed", extra={"session_id": scoped_session_id, "error": str(exc)})
        scoped_errors.append(f"Issue agent failed: {exc}")
        return {"problems_created": 0, "solutions_written": 0, "edges_written": 0}, scoped_errors

    try:
        engine = GraphUpsertEngine(neo4j=neo4j_client, chroma=chroma_client)
        summary = engine.upsert_v2(
            session=_session_node_from_normalized(scoped_session, scoped_transcript),
            user_id=scoped_user_id,
            issue_output=issue_output,
            solution_output=solution_output,
            scope=scope,
            user_email=user_email,
            contributed_by=contributed_by,
        )
    except Exception as exc:
        logger.error("upsert_v2_failed", extra={"session_id": scoped_session_id, "error": str(exc)})
        scoped_errors.append(f"Writer failed: {exc}")
        return {"problems_created": 0, "solutions_written": 0, "edges_written": 0}, scoped_errors

    return {
        "problems_created": summary.problems_created,
        "solutions_written": summary.solutions_written,
        "edges_written": summary.edges_written,
    }, scoped_errors


async def run_extraction_pipeline(
    *,
    session_id: str,
    user_id: str,
    transcript: str,
    neo4j_client: Any,
    chroma_client: Any,
    source: SourceType | str = SourceType.CURSOR,
    normalized_session: NormalizedSession | None = None,
    contribute_to_global: bool = True,
    pii_llm: Any | None = None,
    known_pii: list[str] | None = None,
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
    normalized = normalized_session or normalize_ingestion_request(
        SessionIngestionRequest(
            transcript=transcript,
            source=source.value if isinstance(source, SourceType) else str(source),
            user_id=user_id,
            session_id=session_id,
        )
    )
    transcript = normalized.transcript

    user_summary, user_errors = await _run_for_scope(
        scoped_session=normalized,
        scoped_transcript=transcript,
        scoped_user_id=user_id,
        scope="user",
        neo4j_client=neo4j_client,
        chroma_client=chroma_client,
        user_email=normalized.user_email,
    )
    errors.extend(user_errors)
    if errors:
        return {**user_summary, "errors": errors}

    global_summary: dict[str, int] | None = None
    if contribute_to_global:
        pii_values = [value for value in [normalized.user_id, normalized.user_email, *normalized.participant_ids] if value]
        if known_pii:
            pii_values.extend(known_pii)
        scrubbed_transcript = await scrub_pii_transcript(transcript, llm=pii_llm, known_pii=pii_values)
        global_summary, global_errors = await _run_for_scope(
            scoped_session=_global_session_from(normalized, scrubbed_transcript),
            scoped_transcript=scrubbed_transcript,
            scoped_user_id="global",
            scope="global",
            neo4j_client=neo4j_client,
            chroma_client=chroma_client,
            contributed_by=normalized.user_email or normalized.user_id,
        )
        errors.extend(f"Global {error}" for error in global_errors)

    return {
        **user_summary,
        "global": global_summary,
        "errors": errors,
    }
