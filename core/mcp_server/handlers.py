from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any

from core.agents.orchestrator import run_extraction_pipeline
from core.graph_schema_v2 import SourceType
from core.graph_upsert.dedup import get_or_create_global_collection, get_or_create_user_collection
from core.ingestion import SessionIngestionRequest, normalize_ingestion_request
from core.mcp_server.models import MatchedNode, RecallMemoryRequest, RecallMemoryResponse, StoreSessionRequest, StoreSessionResponse
from core.source_registry import get_source_config

logger = logging.getLogger(__name__)

_STORE_SESSION_CACHE: dict[tuple[str, str, str, str], StoreSessionResponse] = {}


def _clean_org_id(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")


def _run_neo4j(neo4j: object, query: str, **params: Any) -> Any:
    if hasattr(neo4j, "run"):
        return neo4j.run(query, **params)
    if hasattr(neo4j, "session"):
        with neo4j.session() as session:
            result = session.run(query, **params)
            if hasattr(result, "data"):
                rows = result.data()
                return rows[0] if rows else None
            return result
    raise ValueError("Neo4j client must expose run(...) or session().")


async def _run_neo4j_async(neo4j: object, query: str, **params: Any) -> Any:
    return await asyncio.to_thread(_run_neo4j, neo4j, query, **params)


def _single_record(result: Any) -> dict[str, Any] | None:
    if result is None:
        return None
    if hasattr(result, "single"):
        record = result.single()
        return dict(record) if record else None
    if isinstance(result, dict):
        return result
    return None


def _parse_source(value: str) -> SourceType:
    try:
        source = SourceType(str(value or "").strip().lower())
    except ValueError as exc:
        raise ValueError(f"source is invalid: {value!r}") from exc
    get_source_config(source)
    return source


async def _fetch_insight_node(neo4j: object, node_id: str) -> dict | None:
    return _single_record(
        await _run_neo4j_async(
            neo4j,
            """
            MATCH (i:Insight {node_id: $node_id})
            OPTIONAL MATCH (session:Session)-[:PRODUCED]->(i)
            OPTIONAL MATCH (i)-[:SIMILAR_TO]->(similar:Insight)
            RETURN
              i.display_label AS display_label,
              i.display_summary AS display_summary,
              i.memory_kind AS memory_kind,
              i.org_id AS org_id,
              i.company AS company,
              i.what AS what,
              i.why AS why,
              i.how AS how,
              i.outcome AS outcome,
              i.tags AS tags,
              i.raw_session_id AS raw_session_id,
              session.title AS session_title,
              session.summary AS session_summary,
              collect(DISTINCT similar.display_label) AS similar_insights
            """,
            node_id=node_id,
        )
    )


async def handle_recall_memory(
    req: RecallMemoryRequest, *, neo4j: object, chroma: object
) -> RecallMemoryResponse:
    query = (req.query or "").strip()
    if not query:
        raise ValueError("query is required")
    user_id = (req.user_id or "").strip()
    if not user_id:
        raise ValueError("user_id is required")
    user_email = (getattr(req, "user_email", None) or "").strip().lower()
    org_id = _clean_org_id(getattr(req, "org_id", None) or getattr(req, "company", None))
    scope = (getattr(req, "scope", "both") or "both").strip().lower()
    if scope not in {"user", "global", "both"}:
        raise ValueError("scope must be one of: user, global, both")
    _parse_source(req.source)
    min_score = float(getattr(req, "min_score", 0.70))

    scoped_results: list[tuple[str, dict, float]] = []
    if scope in {"user", "both"}:
        scoped_results.extend(
            _query_user_vectors(
                chroma=chroma,
                query=query,
                user_id=user_id,
                user_email=user_email,
                limit=3,
            )
        )
    if scope in {"global", "both"}:
        scoped_results.extend(_query_global_vectors(chroma=chroma, query=query, limit=3, org_id=org_id))

    matched_nodes: list[MatchedNode] = []
    node_ids_used: list[str] = []
    by_label: dict[str, MatchedNode] = {}

    for vector_id, metadata, distance in scoped_results:
        if not vector_id or not isinstance(metadata, dict):
            continue
        if metadata.get("node_type") != "Insight":
            continue
        vector_scope = str(metadata.get("scope") or "user").strip().lower()
        neo4j_node_id = str(metadata.get("neo4j_node_id") or metadata.get("node_id") or vector_id).strip()
        if not neo4j_node_id:
            continue
        similarity_score = round(1.0 - float(distance), 4) if distance is not None else 0.0
        threshold = min(min_score, 0.55) if vector_scope == "global" else min_score
        if similarity_score < threshold:
            continue

        row = await _fetch_insight_node(neo4j, node_id=neo4j_node_id)
        if row is None:
            continue

        neighborhood_keys = ["raw_session_id", "session_title", "session_summary", "similar_insights"]
        neighborhood = {key: row.get(key) for key in neighborhood_keys}
        node_data = {key: value for key, value in row.items() if key not in neighborhood_keys}
        label_key = str(node_data.get("display_label") or node_data.get("what") or metadata.get("canonical_label") or "").strip().lower()
        existing_match = by_label.get(label_key) if label_key else None
        if existing_match is not None:
            if existing_match.source == "user" and vector_scope == "global":
                existing_match.also_available_in_global = True
                existing_match.node_data["global_exists"] = True
                continue
            if existing_match.source == "global" and vector_scope == "user":
                try:
                    matched_nodes.remove(existing_match)
                except ValueError:
                    pass
            else:
                continue

        node_ids_used.append(neo4j_node_id)
        match = MatchedNode(
            node_type="Insight",
            similarity_score=similarity_score,
            node_data=node_data,
            neighborhood=neighborhood,
            source="global" if vector_scope == "global" else "user",
        )
        matched_nodes.append(match)
        if label_key:
            by_label[label_key] = match

    return RecallMemoryResponse(query=query, matched_nodes=matched_nodes, node_ids_used=node_ids_used)


def _query_user_vectors(
    *,
    chroma: object,
    query: str,
    user_id: str,
    user_email: str,
    limit: int,
) -> list[tuple[str, dict, float]]:
    collection = get_or_create_user_collection(chroma)
    identity_filter = {"user_email": user_email} if user_email else {"user_id": user_id}
    try:
        result = collection.query(query_texts=[query], n_results=limit, where={"scope": "user", **identity_filter})
    except Exception:
        raw = collection.query(query_texts=[query], n_results=max(10, limit))
        result = _filter_user_hits(raw, user_id=user_id, user_email=user_email, limit=limit)
    else:
        result = _filter_user_hits(result, user_id=user_id, user_email=user_email, limit=limit)
    return _flatten_chroma_hits(result, default_scope="user")


def _query_global_vectors(*, chroma: object, query: str, limit: int, org_id: str = "") -> list[tuple[str, dict, float]]:
    if not org_id:
        return []
    collection = get_or_create_global_collection(chroma)
    try:
        result = collection.query(query_texts=[query], n_results=limit, where={"scope": "global", "org_id": org_id})
    except Exception:
        try:
            result = collection.query(query_texts=[query], n_results=max(10, limit))
        except Exception:
            return []
    return [
        (node_id, {**metadata, "scope": "global"}, distance)
        for node_id, metadata, distance in _flatten_chroma_hits(result, default_scope="global")
        if metadata.get("scope") in (None, "global") and metadata.get("org_id") == org_id
    ][:limit]


def _flatten_chroma_hits(result: dict, *, default_scope: str) -> list[tuple[str, dict, float]]:
    ids = (result or {}).get("ids") or [[]]
    metadatas = (result or {}).get("metadatas") or [[]]
    distances = (result or {}).get("distances") or [[]]

    hits: list[tuple[str, dict, float]] = []
    rows = zip(ids[0] if ids else [], metadatas[0] if metadatas else [], distances[0] if distances else [])
    for node_id, metadata, distance in rows:
        clean_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        clean_metadata.setdefault("scope", default_scope)
        hits.append((str(node_id), clean_metadata, float(distance)))
    return hits


def _filter_user_hits(raw_result: dict, *, user_id: str, user_email: str = "", limit: int) -> dict:
    ids = (raw_result or {}).get("ids") or [[]]
    metadatas = (raw_result or {}).get("metadatas") or [[]]
    distances = (raw_result or {}).get("distances") or [[]]

    out_ids: list[str] = []
    out_meta: list[dict] = []
    out_dist: list[float] = []

    rows = zip(ids[0] if ids else [], metadatas[0] if metadatas else [], distances[0] if distances else [])
    for node_id, metadata, distance in rows:
        if len(out_ids) >= limit:
            break
        if not isinstance(metadata, dict):
            metadata = {}
        if metadata.get("scope") not in (None, "user"):
            continue
        metadata_email = str(metadata.get("user_email") or "").strip().lower()
        metadata_user_id = str(metadata.get("user_id") or "").strip()
        if user_email and metadata_email:
            if metadata_email != user_email:
                continue
        elif metadata_user_id and metadata_user_id != user_id:
            continue
        out_ids.append(str(node_id))
        out_meta.append(metadata)
        out_dist.append(float(distance))

    return {"ids": [out_ids], "metadatas": [out_meta], "distances": [out_dist]}


def _clean_string_list(values: list[str] | None) -> list[str]:
    return [str(value).strip() for value in (values or []) if str(value).strip()]


def _store_session_fingerprint(normalized_transcript: str) -> str:
    return hashlib.sha256(normalized_transcript.encode()).hexdigest()[:16]


def _structured_completion_context(req: StoreSessionRequest) -> str:
    sections: list[str] = []
    summary = (req.summary or "").strip()
    key_entities = _clean_string_list(req.key_entities)
    decisions = _clean_string_list(req.decisions)
    problems_solved = _clean_string_list(req.problems_solved)

    if summary:
        sections.append(f"Summary: {summary}")
    if key_entities:
        sections.append("Key entities:\n" + "\n".join(f"- {item}" for item in key_entities))
    if decisions:
        sections.append("Decisions:\n" + "\n".join(f"- {item}" for item in decisions))
    if problems_solved:
        sections.append("Problems solved:\n" + "\n".join(f"- {item}" for item in problems_solved))
    if req.session_duration_turns:
        sections.append(f"Approximate session duration turns: {int(req.session_duration_turns)}")

    if not sections:
        return ""
    return "Caller-provided structured session summary:\n" + "\n\n".join(sections)


async def handle_store_session(
    req: StoreSessionRequest,
    *,
    neo4j: object,
    chroma: object,
    llm: object | None,
    postgres_store: object | None = None,
) -> StoreSessionResponse:
    transcript = (req.transcript or "").strip()
    structured_context = _structured_completion_context(req)
    if not transcript and not req.messages and structured_context:
        transcript = structured_context
    if not transcript and not req.messages:
        raise ValueError("transcript is required")
    source = _parse_source(req.source)
    metadata = {
        **(req.metadata or {}),
        "client_metadata": req.client_metadata or {},
        "tool_metadata": req.tool_metadata or {},
    }
    if structured_context:
        metadata["structured_completion_context"] = structured_context
    if req.summary:
        metadata["summary"] = req.summary.strip()
    if req.key_entities:
        metadata["key_entities"] = _clean_string_list(req.key_entities)
    if req.decisions:
        metadata["decisions"] = _clean_string_list(req.decisions)
    if req.problems_solved:
        metadata["problems_solved"] = _clean_string_list(req.problems_solved)
    if req.worth_storing is not None:
        metadata["worth_storing"] = bool(req.worth_storing)
    scope_override = (req.scope or "").strip().lower() or None
    if scope_override and scope_override not in {"user", "global", "both"}:
        raise ValueError("scope must be one of: user, global, both")
    if scope_override:
        metadata["scope_override"] = scope_override
    if req.session_duration_turns:
        metadata["session_duration_turns"] = int(req.session_duration_turns)
    company = (req.company or metadata.get("company") or "").strip() if isinstance(req.company or metadata.get("company"), str) else ""
    org_id = _clean_org_id(req.org_id or company)
    if company:
        metadata["company"] = company
    normalized = normalize_ingestion_request(
        SessionIngestionRequest(
            transcript=transcript,
            source=source.value,
            user_id=req.user_id,
            user_email=req.user_email,
            session_id=req.session_id,
            external_session_id=req.external_session_id,
            org_id=org_id or req.org_id,
            started_at=req.started_at,
            ended_at=req.ended_at,
            participants=req.participants,
            messages=req.messages,
            client_name=req.client_name or str((req.client_metadata or {}).get("name") or "").strip() or None,
            client_version=req.client_version or str((req.client_metadata or {}).get("version") or "").strip() or None,
            source_url=req.source_url,
            metadata=metadata,
        )
    )
    session_id = normalized.session_id
    user_id = normalized.user_email or normalized.user_id
    if not user_id:
        raise ValueError("user_id or user_email is required")

    cache_key = (user_id, session_id, source.value, _store_session_fingerprint(normalized.transcript))
    if cache_key in _STORE_SESSION_CACHE:
        return _STORE_SESSION_CACHE[cache_key]

    stored_ingestion_id: str | None = None
    if postgres_store is not None and hasattr(postgres_store, "record_normalized_session"):
        try:
            stored = postgres_store.record_normalized_session(normalized, status="received")
            stored_ingestion_id = getattr(stored, "ingestion_id", None)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "postgres_ingestion_record_failed",
                extra={"session_id": session_id, "user_id": user_id, "error": str(exc)},
            )

    try:
        result = await run_extraction_pipeline(
            session_id=session_id,
            user_id=user_id,
            transcript=normalized.transcript,
            source=source,
            normalized_session=normalized,
            neo4j_client=neo4j,
            chroma_client=chroma,
            contribute_to_global=req.contribute_to_global,
            pii_llm=llm,
            force_worth_storing=req.worth_storing is True,
            scope_override=scope_override,
        )
    except Exception:
        if postgres_store is not None and stored_ingestion_id and hasattr(postgres_store, "mark_session_status"):
            try:
                postgres_store.mark_session_status(ingestion_id=stored_ingestion_id, status="failed")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "postgres_ingestion_status_failed",
                    extra={"session_id": session_id, "status": "failed", "error": str(exc)},
                )
        raise

    if postgres_store is not None and stored_ingestion_id and hasattr(postgres_store, "mark_session_status"):
        try:
            postgres_store.mark_session_status(ingestion_id=stored_ingestion_id, status="processed")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "postgres_ingestion_status_failed",
                extra={"session_id": session_id, "status": "processed", "error": str(exc)},
            )

    response = StoreSessionResponse(
        session_id=session_id,
        insights_stored=result.get("insights_stored", 0),
        skipped_reason=result.get("skipped_reason"),
        errors=list(result.get("errors") or []),
    )
    _STORE_SESSION_CACHE[cache_key] = response
    return response
