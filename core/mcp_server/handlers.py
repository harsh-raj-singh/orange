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
from core.graph_upsert.dedup import get_or_create_orange_collection
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


async def handle_ping_context(
    req: PingContextRequest, *, neo4j: object, chroma: object
) -> PingContextResponse:

    query = (req.query or "").strip()
    if not query:
        raise ValueError("query is required")
    user_id = (req.user_id or "").strip()
    if not user_id:
        raise ValueError("user_id is required")
    _parse_source(req.source)

    collection = get_or_create_orange_collection(chroma)

    # Step 1: Chroma semantic search — top 3, scoped to user
    try:
        result = collection.query(
            query_texts=[query],
            n_results=3,
            where={"user_id": user_id},
        )
    except Exception:
        raw = collection.query(query_texts=[query], n_results=10)
        result = _filter_user_hits(raw, user_id=user_id, limit=3)

    ids = (result or {}).get("ids") or [[]]
    metadatas = (result or {}).get("metadatas") or [[]]
    distances = (result or {}).get("distances") or [[]]

    matched_nodes: list[MatchedNode] = []
    node_ids_used: list[str] = []

    # Step 2: For each Chroma hit, fetch full node + neighborhood from Neo4j
    for vector_id, metadata, distance in zip(
        ids[0] if ids else [],
        metadatas[0] if metadatas else [],
        distances[0] if distances else [],
    ):
        if not vector_id:
            continue

        node_type = metadata.get("node_type", "").strip() if isinstance(metadata, dict) else ""
        neo4j_node_id = (
            str(metadata.get("neo4j_node_id") or vector_id).strip()
            if isinstance(metadata, dict)
            else str(vector_id).strip()
        )
        if not neo4j_node_id:
            continue
        similarity_score = round(1.0 - float(distance), 4) if distance is not None else 0.0

        # Step 3: Type-aware Neo4j fetch
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
        else:
            continue  # skip unknown node types

        if row is None:
            continue

        # Step 4: Split row into node_data and neighborhood
        neighborhood = {k: row.get(k) for k in neighborhood_keys}
        node_data = {k: v for k, v in row.items() if k not in neighborhood_keys}

        node_ids_used.append(neo4j_node_id)
        matched_nodes.append(
            MatchedNode(
                node_type=node_type,
                similarity_score=similarity_score,
                node_data=node_data,
                neighborhood=neighborhood,
            )
        )

    return PingContextResponse(
        query=query,
        matched_nodes=matched_nodes,
        node_ids_used=node_ids_used,
    )


def _filter_user_hits(raw_result: dict, *, user_id: str, limit: int) -> dict:
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
        if isinstance(metadata, dict) and metadata.get("user_id") not in (None, user_id):
            continue
        out_ids.append(str(node_id))
        out_meta.append(metadata if isinstance(metadata, dict) else {})
        out_dist.append(float(distance))

    return {"ids": [out_ids], "metadatas": [out_meta], "distances": [out_dist]}


async def handle_store_session(
    req: StoreSessionRequest,
    *,
    neo4j: object,
    chroma: object,
    llm: object | None,
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
    user_id = normalized.user_id
    if not user_id:
        raise ValueError("user_id is required")

    cache_key = (user_id, session_id, source.value)
    if cache_key in _STORE_SESSION_CACHE:
        return _STORE_SESSION_CACHE[cache_key]

    result = await run_extraction_pipeline(
        session_id=session_id,
        user_id=user_id,
        transcript=normalized.transcript,
        source=source,
        normalized_session=normalized,
        neo4j_client=neo4j,
        chroma_client=chroma,
    )

    response = StoreSessionResponse(
        session_id=session_id,
        problems_created=result.get("problems_created", 0),
        problems_merged=result.get("problems_merged", 0),
        solutions_written=result.get("solutions_written", 0),
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
