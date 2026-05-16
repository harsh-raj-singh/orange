from __future__ import annotations

import logging

from core.agents.orchestrator import run_extraction_pipeline
from core.ingestion import SessionIngestionRequest, normalize_ingestion_request
from core.graph_schema_v2 import (
    ConfidenceLevel,
    Problem,
    ResolvedByEdge,
    Solution,
    SolutionOutcome,
    SourceType,
    validate_edge,
    validate_node,
)
from core.graph_upsert.dedup import (
    get_or_create_global_collection,
    get_or_create_orange_collection,
    get_or_create_user_collection,
)
from core.graph_upsert.embeddings import build_solution_embed_string
from core.graph_upsert.writer import content_hash
from core.mcp_server.models import (
    MatchedNode,
    PingContextRequest,
    PingContextResponse,
    ResolveProblemRequest,
    ResolveProblemResponse,
    StoreSessionRequest,
    StoreSessionResponse,
)
from core.source_registry import get_source_config

logger = logging.getLogger(__name__)

# H6: For now store_session is implemented synchronously (no background queue)
# to keep deterministic behavior in tests. Production can switch to async queueing.
_STORE_SESSION_CACHE: dict[tuple[str, str, str], StoreSessionResponse] = {}


def _run_neo4j(neo4j: object, query: str, **params):
    if hasattr(neo4j, "run"):
        return neo4j.run(query, **params)
    if hasattr(neo4j, "session"):
        with neo4j.session() as session:
            return session.run(query, **params)
    raise ValueError("Neo4j client must expose run(...) or session().")


def _single_record(result) -> dict | None:
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


def _fetch_problem_node(neo4j, node_id: str) -> dict | None:
    return _single_record(
        _run_neo4j(
            neo4j,
            """
        MATCH (p:Problem {node_id: $node_id})
        OPTIONAL MATCH (p)-[:ATTEMPTED_BY]->(s:Solution)
        OPTIONAL MATCH (p)-[:RESOLVED_BY]->(rs:Solution)
        OPTIONAL MATCH (p)-[:CAUSED_BY]->(parent:Problem)
        OPTIONAL MATCH (child:Problem)-[:CAUSED_BY]->(p)
        OPTIONAL MATCH (p)-[:RELATED_TO]->(related:Problem)
        RETURN
          p.canonical_label AS canonical_label,
          p.description AS description,
          p.error_code AS error_code,
          p.error_type AS error_type,
          p.stack_trace_summary AS stack_trace_summary,
          p.tech_stack AS tech_stack,
          p.affected_file_paths AS affected_file_paths,
          p.relevant_code AS relevant_code,
          p.prior_solution_contexts AS prior_solution_contexts,
          p.depth AS depth,
          p.recurrence_count AS recurrence_count,
          p.first_seen_turn AS first_seen_turn,
          p.last_seen_turn AS last_seen_turn,
          collect(DISTINCT {
            canonical_label: s.canonical_label,
            description: s.description,
            in_depth_summary: s.in_depth_summary,
            outcome: s.outcome,
            failure_reason: s.failure_reason,
            steps: s.steps,
            code_snippets: s.code_snippets,
            attempt_number: s.attempt_number
          }) AS attempted_solutions,
          rs.canonical_label AS resolved_by,
          parent.canonical_label AS caused_by_parent,
          collect(DISTINCT child.canonical_label) AS child_problems,
          collect(DISTINCT related.canonical_label) AS related_problems
        """,
            node_id=node_id,
        )
    )


def _fetch_solution_node(neo4j, node_id: str) -> dict | None:
    return _single_record(
        _run_neo4j(
            neo4j,
            """
        MATCH (s:Solution {node_id: $node_id})
        OPTIONAL MATCH (problem:Problem)-[:ATTEMPTED_BY]->(s)
        OPTIONAL MATCH (s)-[:REFINED_BY]->(parent_sol:Solution)
        OPTIONAL MATCH (child_sol:Solution)-[:REFINED_BY]->(s)
        RETURN
          s.canonical_label AS canonical_label,
          s.description AS description,
          s.in_depth_summary AS in_depth_summary,
          s.outcome AS outcome,
          s.failure_reason AS failure_reason,
          s.failure_error_code AS failure_error_code,
          s.steps AS steps,
          s.code_snippets AS code_snippets,
          s.tools_used AS tools_used,
          s.attempt_number AS attempt_number,
          problem.canonical_label AS addresses_problem,
          problem.description AS problem_description,
          problem.error_code AS problem_error_code,
          problem.tech_stack AS problem_tech_stack,
          parent_sol.canonical_label AS refined_from,
          collect(DISTINCT child_sol.canonical_label) AS refined_into
        """,
            node_id=node_id,
        )
    )


def _fetch_insight_node(neo4j, node_id: str) -> dict | None:
    return _single_record(
        _run_neo4j(
            neo4j,
            """
        MATCH (i:Insight {node_id: $node_id})
        OPTIONAL MATCH (session:Session)-[:PRODUCED]->(i)
        OPTIONAL MATCH (i)-[:SIMILAR_TO]->(similar:Insight)
        RETURN
          i.display_label AS display_label,
          i.display_summary AS display_summary,
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


async def handle_ping_context(
    req: PingContextRequest, *, neo4j: object, chroma: object
) -> PingContextResponse:
    query = (req.query or "").strip()
    if not query:
        raise ValueError("query is required")
    user_id = (req.user_id or "").strip()
    if not user_id:
        raise ValueError("user_id is required")
    user_email = (getattr(req, "user_email", None) or "").strip().lower()
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
        scoped_results.extend(_query_global_vectors(chroma=chroma, query=query, limit=3))

    matched_nodes: list[MatchedNode] = []
    node_ids_used: list[str] = []
    by_label: dict[str, MatchedNode] = {}

    for vector_id, metadata, distance in scoped_results:
        if not vector_id:
            continue

        node_type = metadata.get("node_type", "").strip() if isinstance(metadata, dict) else ""
        vector_scope = str(metadata.get("scope") or "user").strip().lower() if isinstance(metadata, dict) else "user"
        neo4j_node_id = (
            str(metadata.get("neo4j_node_id") or vector_id).strip()
            if isinstance(metadata, dict)
            else str(vector_id).strip()
        )
        if not neo4j_node_id:
            continue
        similarity_score = round(1.0 - float(distance), 4) if distance is not None else 0.0
        threshold = 0.72 if vector_scope == "global" else min_score
        if similarity_score < threshold:
            continue

        if node_type == "Problem":
            row = _fetch_problem_node(neo4j, node_id=neo4j_node_id)
            neighborhood_keys = [
                "attempted_solutions",
                "resolved_by",
                "caused_by_parent",
                "child_problems",
                "related_problems",
            ]
        elif node_type == "Solution":
            row = _fetch_solution_node(neo4j, node_id=neo4j_node_id)
            neighborhood_keys = [
                "addresses_problem",
                "problem_description",
                "problem_error_code",
                "problem_tech_stack",
                "refined_from",
                "refined_into",
            ]
        elif node_type == "Insight":
            row = _fetch_insight_node(neo4j, node_id=neo4j_node_id)
            neighborhood_keys = [
                "raw_session_id",
                "session_title",
                "session_summary",
                "similar_insights",
            ]
        else:
            continue

        if row is None:
            continue

        neighborhood = {k: row.get(k) for k in neighborhood_keys}
        node_data = {
            k: v
            for k, v in row.items()
            if k not in neighborhood_keys and not (vector_scope == "global" and k == "contributed_by")
        }
        label_key = str(
            node_data.get("canonical_label")
            or node_data.get("display_label")
            or node_data.get("what")
            or metadata.get("canonical_label")
            or ""
        ).strip().lower()
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
            node_type=node_type,
            similarity_score=similarity_score,
            node_data=node_data,
            neighborhood=neighborhood,
            source="global" if vector_scope == "global" else "user",
        )
        matched_nodes.append(match)
        if label_key:
            by_label[label_key] = match

    return PingContextResponse(
        query=query,
        matched_nodes=matched_nodes,
        node_ids_used=node_ids_used,
    )


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
        result = collection.query(
            query_texts=[query],
            n_results=limit,
            where={"scope": "user", **identity_filter},
        )
    except Exception:
        raw = collection.query(query_texts=[query], n_results=max(10, limit))
        result = _filter_user_hits(raw, user_id=user_id, user_email=user_email, limit=limit)
    else:
        result = _filter_user_hits(result, user_id=user_id, user_email=user_email, limit=limit)
    return _flatten_chroma_hits(result, default_scope="user")


def _query_global_vectors(*, chroma: object, query: str, limit: int) -> list[tuple[str, dict, float]]:
    collection = get_or_create_global_collection(chroma)
    try:
        result = collection.query(query_texts=[query], n_results=limit)
    except Exception:
        return []
    return [
        (node_id, {**metadata, "scope": "global"}, distance)
        for node_id, metadata, distance in _flatten_chroma_hits(result, default_scope="global")
        if metadata.get("scope") in (None, "global")
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


async def handle_store_session(
    req: StoreSessionRequest,
    *,
    neo4j: object,
    chroma: object,
    llm: object | None,
    postgres_store: object | None = None,
) -> StoreSessionResponse:
    transcript = (req.transcript or "").strip()
    if not transcript and not req.messages:
        raise ValueError("transcript is required")
    source = _parse_source(req.source)
    metadata = {
        **(req.metadata or {}),
        "client_metadata": req.client_metadata or {},
        "tool_metadata": req.tool_metadata or {},
    }
    normalized = normalize_ingestion_request(
        SessionIngestionRequest(
            transcript=transcript,
            source=source.value,
            user_id=req.user_id,
            user_email=req.user_email,
            session_id=req.session_id,
            external_session_id=req.external_session_id,
            org_id=req.org_id,
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

    cache_key = (user_id, session_id, source.value)
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
        )
    except Exception:
        if (
            postgres_store is not None
            and stored_ingestion_id
            and hasattr(postgres_store, "mark_session_status")
        ):
            try:
                postgres_store.mark_session_status(ingestion_id=stored_ingestion_id, status="failed")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "postgres_ingestion_status_failed",
                    extra={"session_id": session_id, "status": "failed", "error": str(exc)},
                )
        raise

    if (
        postgres_store is not None
        and stored_ingestion_id
        and hasattr(postgres_store, "mark_session_status")
    ):
        try:
            postgres_store.mark_session_status(ingestion_id=stored_ingestion_id, status="processed")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "postgres_ingestion_status_failed",
                extra={"session_id": session_id, "status": "processed", "error": str(exc)},
            )

    response = StoreSessionResponse(
        session_id=session_id,
        problems_created=result.get("problems_created", 0),
        problems_merged=result.get("problems_merged", 0),
        solutions_written=result.get("solutions_written", 0),
        insights_stored=result.get("insights_stored", 0),
        skipped_reason=result.get("skipped_reason"),
        errors=list(result.get("errors") or []),
    )
    _STORE_SESSION_CACHE[cache_key] = response
    return response


async def handle_resolve_problem(
    req: ResolveProblemRequest,
    *,
    neo4j: object,
    chroma: object,
) -> ResolveProblemResponse:
    session_id = (req.session_id or "").strip()
    user_id = (req.user_id or "").strip()
    label = " ".join((req.problem_label or "").split()).lower()
    solution_text = " ".join((req.solution_that_worked or "").split())

    if not session_id:
        raise ValueError("session_id is required")
    if not user_id:
        raise ValueError("user_id is required")
    if not label:
        raise ValueError("problem_label is required")
    if not solution_text:
        raise ValueError("solution_that_worked is required")

    problem_row = _single_record(
        _run_neo4j(
            neo4j,
            """
            // H6:FIND_PROBLEM_BY_LABEL
            MATCH (p:Problem {user_id: $user_id})
            WHERE p.canonical_label = $label
            RETURN p.node_id AS node_id,
                   p.canonical_label AS canonical_label,
                   coalesce(p.context_brief, '') AS context_brief,
                   coalesce(p.status, 'open') AS status
            LIMIT 1
            """,
            user_id=user_id,
            label=label,
        )
    )

    if not problem_row:
        return ResolveProblemResponse(resolved=False, problem_node_id=None, solution_node_id=None)

    problem_id = str(problem_row["node_id"])

    problem_node = Problem(
        node_id=problem_id,
        canonical_label=str(problem_row.get("canonical_label") or label),
        description=str(problem_row.get("context_brief") or ""),
    )
    validate_node(problem_node)

    canonical_solution_label = " ".join(solution_text.lower().split())
    solution_node = Solution(
        canonical_label=canonical_solution_label,
        description=solution_text,
        in_depth_summary=solution_text,
        outcome=SolutionOutcome.SUCCESS,
        confidence=ConfidenceLevel.HIGH,
    )
    validate_node(solution_node)

    solution_hash = content_hash("Solution", session_id, canonical_solution_label)
    solution_id = str(
        (_single_record(
            _run_neo4j(
                neo4j,
                """
                // H6:UPSERT_RESOLVE_SOLUTION
                MERGE (s:Solution {canonical_label: $canonical_label, parent_problem_id: $problem_id, user_id: $user_id})
                ON CREATE SET s.node_id = $node_id
                SET s.description = $description,
                    s.in_depth_summary = $description,
                    s.outcome = 'success',
                    s.confidence = 'high',
                    s.content_hash = $content_hash,
                    s.status = 'resolved'
                RETURN s.node_id AS node_id
                """,
                canonical_label=canonical_solution_label,
                description=solution_text,
                user_id=user_id,
                problem_id=problem_id,
                node_id=solution_node.node_id,
                content_hash=solution_hash,
            )
        )
        or {"node_id": solution_node.node_id})["node_id"]
    )

    persisted_solution = Solution(
        node_id=solution_id,
        canonical_label=canonical_solution_label,
        description=solution_text,
        in_depth_summary=solution_text,
        outcome=SolutionOutcome.SUCCESS,
        confidence=ConfidenceLevel.HIGH,
    )

    validate_edge(ResolvedByEdge(), problem_node, persisted_solution)
    _run_neo4j(
        neo4j,
        """
        // H6:EDGE_RESOLVED_BY
        MATCH (p:Problem {node_id: $problem_id, user_id: $user_id})
        MATCH (s:Solution {node_id: $solution_id, user_id: $user_id})
        MERGE (p)-[:RESOLVED_BY]->(s)
        """,
        problem_id=problem_id,
        solution_id=solution_id,
        user_id=user_id,
    )

    _run_neo4j(
        neo4j,
        """
        // H6:SET_PROBLEM_RESOLVED
        MATCH (p:Problem {node_id: $problem_id, user_id: $user_id})
        SET p.status = 'resolved'
        """,
        problem_id=problem_id,
        user_id=user_id,
    )

    collection = get_or_create_orange_collection(chroma)
    metadata = {
        "node_type": "Solution",
        "user_id": user_id,
        "user_email": user_id,
        "scope": "user",
        "neo4j_node_id": solution_id,
        "canonical_label": canonical_solution_label,
        "context_brief": solution_text,
    }
    collection.upsert(
        ids=[f"solution_{solution_id}"],
        documents=[build_solution_embed_string(persisted_solution)],
        metadatas=[metadata],
    )

    return ResolveProblemResponse(
        resolved=True,
        problem_node_id=problem_id,
        solution_node_id=solution_id,
    )
