"""
Entry point for post-chat extraction pipeline.
Called when user marks a chat as complete.

Execution order:
1. Triage Agent decides whether the completed session produced durable knowledge
2. Insight Extractor reads the full session transcript
3. upsert_insights writes unified Insight nodes to Neo4j + Chroma
"""
import logging
from datetime import datetime, timezone
from typing import Any

from core.agents.insight_extractor import extract_insights
from core.agents.pii_scrubber import scrub_pii_transcript
from core.agents.triage import run_triage_agent
from core.ingestion import NormalizedSession, SessionIngestionRequest, normalize_ingestion_request
from core.graph_upsert.writer import GraphUpsertEngine
from core.graph_schema_v2 import Insight, InsightOutcome, Session, SourceType

logger = logging.getLogger(__name__)


def _session_node_from_normalized(scoped_session: NormalizedSession, summary: str) -> Session:
    started_at = scoped_session.started_at or scoped_session.ingested_at or datetime.now(timezone.utc)
    return Session(
        node_id=scoped_session.session_node_id,
        source=scoped_session.source,
        started_at=started_at,
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


def _insight_outcome(value: str) -> InsightOutcome:
    try:
        return InsightOutcome(str(value or "").strip().lower())
    except ValueError:
        return InsightOutcome.EXPLORATORY


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
    run_triage: bool = True,
) -> tuple[dict[str, int | str | None], list[str]]:
    scoped_errors: list[str] = []
    scoped_session_id = scoped_session.session_id

    if run_triage:
        try:
            triage = await run_triage_agent(scoped_transcript)
        except Exception as exc:
            logger.error("triage_agent_failed", extra={"session_id": scoped_session_id, "error": str(exc)})
            scoped_errors.append(f"Triage agent failed: {exc}")
            return {"insights_stored": 0, "edges_written": 0, "skipped_reason": "triage failed"}, scoped_errors

        if not triage.worth_storing:
            logger.info(
                "store_session_triage_skipped",
                extra={"session_id": scoped_session_id, "scope": scope, "reason": triage.reason},
            )
            return {"insights_stored": 0, "edges_written": 0, "skipped_reason": triage.reason}, scoped_errors

    drafts = await extract_insights(scoped_transcript)
    if not drafts:
        reason = "Insight extractor returned no durable insights."
        logger.info("store_session_insights_empty", extra={"session_id": scoped_session_id, "scope": scope})
        return {"insights_stored": 0, "edges_written": 0, "skipped_reason": reason}, scoped_errors

    session = _session_node_from_normalized(scoped_session, scoped_transcript)
    insights = [
        Insight(
            scope="global" if scope == "global" else "user",
            user_id=scoped_user_id if scope == "user" else None,
            user_email=user_email if scope == "user" else None,
            contributed_by=contributed_by if scope == "global" else None,
            what=draft.what,
            why=draft.why,
            how=draft.how,
            outcome=_insight_outcome(draft.outcome),
            tags=list(draft.tags or []),
            display_label=draft.display_label,
            display_summary=draft.display_summary,
            raw_session_id=session.node_id,
            source=session.source,
        )
        for draft in drafts
    ]

    try:
        engine = GraphUpsertEngine(neo4j=neo4j_client, chroma=chroma_client)
        summary = engine.upsert_insights(
            session=session,
            user_id=scoped_user_id,
            insights=insights,
            scope=scope,
            user_email=user_email,
            contributed_by=contributed_by,
        )
    except Exception as exc:
        logger.error("upsert_insights_failed", extra={"session_id": scoped_session_id, "error": str(exc)})
        scoped_errors.append(f"Writer failed: {exc}")
        return {"insights_stored": 0, "edges_written": 0, "skipped_reason": "writer failed"}, scoped_errors

    return {
        "insights_stored": summary.insights_stored,
        "edges_written": summary.edges_written,
        "skipped_reason": None,
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
        dict with keys: insights_stored, skipped_reason, edges_written, errors
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

    if not user_summary.get("insights_stored"):
        return {
            "insights_stored": 0,
            "skipped_reason": user_summary.get("skipped_reason"),
            "edges_written": user_summary.get("edges_written", 0),
            "global": None,
            "errors": errors,
            "problems_created": 0,
            "problems_merged": 0,
            "solutions_written": 0,
        }

    global_summary: dict[str, int | str | None] | None = None
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
            run_triage=False,
        )
        errors.extend(f"Global {error}" for error in global_errors)

    return {
        **user_summary,
        "global": global_summary,
        "errors": errors,
        "problems_created": 0,
        "problems_merged": 0,
        "solutions_written": 0,
    }
