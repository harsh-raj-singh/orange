from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from core.agents.extraction_outputs import (
    EnrichedProblem,
    ExtractedSolution,
    IssueAgentOutput,
    SolutionAgentOutput,
)
from core.graph_schema_v2 import (
    BelongsToEdge,
    Concept,
    ConceptCategory,
    HasProblemEdge,
    NodeType,
    Problem,
    ProposedForEdge,
    RecursAsEdge,
    RelatedToEdge,
    ResolvedByEdge,
    Session,
    Solution,
    SolutionOutcome,
    SourceType,
    validate_edge,
    validate_node,
)
from core.graph_upsert.dedup import get_or_create_orange_collection, run_dedup
from core.graph_upsert.embeddings import (
    build_concept_embed_string,
    build_problem_embed_string,
    build_solution_embed_string,
)

logger = logging.getLogger(__name__)


@dataclass
class UpsertSummary:
    sessions_written: int = 0
    concepts_written: int = 0
    problems_created: int = 0
    problems_merged: int = 0
    solutions_written: int = 0
    cross_session_links_written: int = 0
    related_to_edges_written: int = 0
    similar_to_edges_written: int = 0
    edges_written: int = 0
    edges_skipped: int = 0
    skipped_by_idempotency: int = 0


def content_hash(node_type: str, session_id: str, canonical_label: str) -> str:
    raw = f"{node_type}:{session_id}:{canonical_label}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _source_value(source: SourceType | str) -> str:
    return source.value if isinstance(source, SourceType) else str(source)


def problem_node_id_for(user_id: str, canonical_label: str) -> str:
    return f"problem_{hashlib.sha256(f'{user_id}:{canonical_label}'.encode()).hexdigest()[:16]}"


def solution_node_id_for(user_id: str, canonical_label: str, attempt_number: int) -> str:
    return (
        f"solution_{hashlib.sha256(f'{user_id}:{canonical_label}:{attempt_number}'.encode()).hexdigest()[:16]}"
    )


class GraphUpsertEngine:
    """H4 graph upsert engine for writing validated extraction output to Neo4j + Chroma."""

    def __init__(self, neo4j: Any, chroma: Any, llm: Any = None) -> None:
        self.neo4j = neo4j
        self.collection = get_or_create_orange_collection(chroma)
        self.llm = llm

    def upsert(
        self,
        *,
        session: Session,
        user_id: str,
        debug_result: Any | None,
        concept_result: Any | None,
    ) -> UpsertSummary:
        summary = UpsertSummary()

        # Step 1: Session node.
        validate_node(session)
        session.node_id = self._merge_session(session=session, user_id=user_id)
        summary.sessions_written += 1

        # Step 2: Concept nodes + Concept->Concept hierarchy edges.
        concept_nodes = self._write_concepts(
            session=session,
            user_id=user_id,
            concept_drafts=(concept_result.concepts if concept_result else []),
            summary=summary,
        )

        if not debug_result:
            return summary

        # Step 3/4: Problem/Solution writes in order.
        for problem_output in debug_result.problems:
            self._write_problem_with_solutions(
                session=session,
                user_id=user_id,
                problem_output=problem_output,
                concept_nodes=concept_nodes,
                summary=summary,
            )

        return summary

    def _create_problem_v2(
        self,
        *,
        problem: EnrichedProblem,
        user_id: str,
        source: SourceType | str,
    ) -> str:
        """
        Writes a Problem node with the new v2 schema fields.
        Uses MERGE so re-runs are idempotent on node_id.
        Returns node_id.
        """
        node_id = problem_node_id_for(user_id, problem.canonical_label)

        self._run_neo4j(
            """
            MERGE (p:Problem {node_id: $node_id, user_id: $user_id})
            SET p.canonical_label       = $canonical_label,
                p.description           = $description,
                p.llm_reasoning         = $llm_reasoning,
                p.error_code            = $error_code,
                p.error_type            = $error_type,
                p.stack_trace_summary   = $stack_trace_summary,
                p.tech_stack            = $tech_stack,
                p.affected_file_paths   = $affected_file_paths,
                p.relevant_code         = $relevant_code,
                p.prior_solution_contexts = $prior_solution_contexts,
                p.depth                 = $depth,
                p.root_cause_known      = $root_cause_known,
                p.root_cause_description = $root_cause_description,
                p.recurrence_count      = coalesce(p.recurrence_count, 0),
                p.turn_sequence         = $turn_sequence,
                p.first_seen_turn       = $first_seen_turn,
                p.last_seen_turn        = $last_seen_turn,
                p.source                = $source,
                p.extraction_version    = 'v2'
            RETURN p.node_id AS node_id
            """,
            node_id=node_id,
            user_id=user_id,
            canonical_label=problem.canonical_label,
            description=problem.description,
            llm_reasoning=problem.llm_reasoning,
            error_code=problem.error_code,
            error_type=problem.error_type,
            stack_trace_summary=problem.stack_trace_summary,
            tech_stack=list(problem.tech_stack),
            affected_file_paths=list(problem.affected_file_paths),
            relevant_code=list(problem.relevant_code),
            prior_solution_contexts=list(problem.prior_solution_contexts),
            depth=problem.depth,
            root_cause_known=problem.root_cause_known,
            root_cause_description=problem.root_cause_description,
            turn_sequence=list(problem.turn_sequence),
            first_seen_turn=problem.first_seen_turn,
            last_seen_turn=problem.last_seen_turn,
            source=_source_value(source),
        )
        return node_id

    def _create_solution_v2(
        self,
        *,
        solution: ExtractedSolution,
        user_id: str,
        source: SourceType | str,
    ) -> str:
        """
        Writes a Solution node with v2 schema fields.
        Returns node_id.
        """
        node_id = solution_node_id_for(user_id, solution.canonical_label, solution.attempt_number)

        self._run_neo4j(
            """
            MERGE (s:Solution {node_id: $node_id, user_id: $user_id})
            SET s.canonical_label        = $canonical_label,
                s.description            = $description,
                s.in_depth_summary       = $in_depth_summary,
                s.outcome                = $outcome,
                s.failure_reason         = $failure_reason,
                s.failure_error_code     = $failure_error_code,
                s.partial_fix_description = $partial_fix_description,
                s.steps                  = $steps,
                s.code_snippets          = $code_snippets,
                s.tools_used             = $tools_used,
                s.attempt_number         = $attempt_number,
                s.addresses_problem_label = $addresses_problem_label,
                s.applied_turn           = $applied_turn,
                s.turn_sequence          = $turn_sequence,
                s.confidence             = $confidence,
                s.source                 = $source,
                s.extraction_version     = 'v2'
            RETURN s.node_id AS node_id
            """,
            node_id=node_id,
            user_id=user_id,
            canonical_label=solution.canonical_label,
            description=solution.description,
            in_depth_summary=solution.in_depth_summary,
            outcome=solution.outcome.value,
            failure_reason=solution.failure_reason,
            failure_error_code=solution.failure_error_code,
            partial_fix_description=solution.partial_fix_description,
            steps=list(solution.steps),
            code_snippets=list(solution.code_snippets),
            tools_used=list(solution.tools_used),
            attempt_number=solution.attempt_number,
            addresses_problem_label=solution.addresses_problem_label,
            applied_turn=solution.applied_turn,
            turn_sequence=list(solution.turn_sequence),
            confidence=solution.confidence.value,
            source=_source_value(source),
        )
        return node_id

    def _run_edge_direct(
        self,
        *,
        from_id: str,
        to_id: str,
        edge_type: str,
        properties: dict,
        summary: UpsertSummary,
    ) -> None:
        """
        Writes a directed edge between two nodes by node_id.
        Bypasses typed edge validation - edge_type must be a valid EdgeType value.
        Uses MERGE so re-runs are idempotent.
        """
        if properties:
            props_cypher = ", ".join(f"r.{key} = ${key}" for key in properties)
            set_clause = f"SET {props_cypher}"
        else:
            set_clause = ""

        query = f"""
            MATCH (a {{node_id: $from_id}}), (b {{node_id: $to_id}})
            MERGE (a)-[r:{edge_type}]->(b)
            {set_clause}
        """

        try:
            self._run_neo4j(query, from_id=from_id, to_id=to_id, **properties)
            summary.edges_written += 1
        except Exception as exc:
            summary.edges_skipped += 1
            logger.warning(
                "edge_write_failed",
                extra={
                    "edge_type": edge_type,
                    "from_id": from_id,
                    "to_id": to_id,
                    "error": str(exc),
                },
            )

    def upsert_v2(
        self,
        *,
        session: Session,
        user_id: str,
        issue_output: IssueAgentOutput,
        solution_output: SolutionAgentOutput,
    ) -> UpsertSummary:
        """
        New pipeline writer. Accepts output from Issue Agent + Solution Agent.
        Old upsert() is untouched - this runs alongside it.
        """
        summary = UpsertSummary()
        label_to_node_id: dict[str, str] = {}

        validate_node(session)
        self._merge_session(session=session, user_id=user_id)
        summary.sessions_written += 1

        # --- PROBLEMS ---
        for problem in issue_output.problems:
            similar_problem = self._find_similar_problem_v2(problem=problem, user_id=user_id)
            node_id = self._create_problem_v2(problem=problem, user_id=user_id, source=session.source)
            label_to_node_id[problem.canonical_label] = node_id
            self._upsert_chroma_document(
                node_type="Problem",
                node_id=node_id,
                user_id=user_id,
                canonical_label=problem.canonical_label,
                context_brief=problem.description[:120],
                document=f"{problem.canonical_label} - {problem.description}".strip(),
                source=session.source,
            )
            summary.problems_created += 1

            self._run_edge_direct(
                from_id=session.node_id,
                to_id=node_id,
                edge_type="HAS_PROBLEM",
                properties={},
                summary=summary,
            )
            if similar_problem and similar_problem["node_id"] != node_id:
                self._run_edge_direct(
                    from_id=node_id,
                    to_id=similar_problem["node_id"],
                    edge_type="SIMILAR_TO",
                    properties={"similarity_score": similar_problem["similarity_score"]},
                    summary=summary,
                )
                summary.similar_to_edges_written += 1

        for problem in issue_output.problems:
            if not problem.parent_segment_id:
                continue
            parent = next(
                (p for p in issue_output.problems if p.segment_id == problem.parent_segment_id),
                None,
            )
            if not parent:
                continue
            child_id = label_to_node_id.get(problem.canonical_label)
            parent_id = label_to_node_id.get(parent.canonical_label)
            if not child_id or not parent_id:
                continue
            if problem.relationship_to_parent:
                props = {}
                if problem.via_solution_label:
                    props["via_solution_label"] = problem.via_solution_label
                self._run_edge_direct(
                    from_id=child_id,
                    to_id=parent_id,
                    edge_type=problem.relationship_to_parent,
                    properties=props,
                    summary=summary,
                )

        ordered = sorted(issue_output.problems, key=lambda p: p.first_seen_turn or 0)
        for i in range(1, len(ordered)):
            prev_id = label_to_node_id.get(ordered[i - 1].canonical_label)
            curr_id = label_to_node_id.get(ordered[i].canonical_label)
            if prev_id and curr_id:
                self._run_edge_direct(
                    from_id=curr_id,
                    to_id=prev_id,
                    edge_type="PRECEDED_BY",
                    properties={},
                    summary=summary,
                )

        # --- SOLUTIONS ---
        for solution in solution_output.solutions:
            node_id = self._create_solution_v2(solution=solution, user_id=user_id, source=session.source)
            label_to_node_id[solution.canonical_label] = node_id
            self._upsert_chroma_document(
                node_type="Solution",
                node_id=node_id,
                user_id=user_id,
                canonical_label=solution.canonical_label,
                context_brief=solution.in_depth_summary[:120],
                document=f"{solution.canonical_label}: {solution.in_depth_summary}".strip(),
                source=session.source,
            )
            summary.solutions_written += 1

            problem_id = label_to_node_id.get(solution.addresses_problem_label)
            if problem_id:
                self._run_edge_direct(
                    from_id=problem_id,
                    to_id=node_id,
                    edge_type="ATTEMPTED_BY",
                    properties={"attempt_number": solution.attempt_number},
                    summary=summary,
                )
                if solution.outcome == SolutionOutcome.SUCCESS:
                    self._run_edge_direct(
                        from_id=problem_id,
                        to_id=node_id,
                        edge_type="RESOLVED_BY",
                        properties={},
                        summary=summary,
                    )

            self._run_edge_direct(
                from_id=node_id,
                to_id=session.node_id,
                edge_type="TRIED_IN",
                properties={},
                summary=summary,
            )

        for solution in solution_output.solutions:
            if solution.parent_solution_label:
                parent_sol_id = label_to_node_id.get(solution.parent_solution_label)
                child_sol_id = label_to_node_id.get(solution.canonical_label)
                if parent_sol_id and child_sol_id:
                    self._run_edge_direct(
                        from_id=child_sol_id,
                        to_id=parent_sol_id,
                        edge_type="REFINED_BY",
                        properties={},
                        summary=summary,
                    )

        return summary

    def _find_similar_problem_v2(
        self,
        *,
        problem: EnrichedProblem,
        user_id: str,
        threshold: float = 0.88,
    ) -> dict[str, Any] | None:
        document = f"{problem.canonical_label} - {problem.description}".strip()
        if not document:
            return None

        try:
            result = self.collection.query(
                query_texts=[document],
                n_results=3,
                where={"node_type": "Problem", "user_id": user_id},
            )
        except Exception:  # noqa: BLE001
            return None

        ids = (result or {}).get("ids") or [[]]
        distances = (result or {}).get("distances") or [[]]
        metadatas = (result or {}).get("metadatas") or [[]]

        for vector_id, distance, metadata in zip(
            ids[0] if ids else [],
            distances[0] if distances else [],
            metadatas[0] if metadatas else [],
        ):
            if not isinstance(metadata, dict):
                continue
            if metadata.get("node_type") != "Problem" or metadata.get("user_id") != user_id:
                continue
            try:
                similarity_score = round(1.0 - float(distance), 4)
            except Exception:  # noqa: BLE001
                continue
            if similarity_score < threshold:
                continue
            node_id = str(metadata.get("neo4j_node_id") or vector_id or "").strip()
            if node_id:
                return {"node_id": node_id, "similarity_score": similarity_score}

        return None

    def _write_concepts(
        self,
        *,
        session: Session,
        user_id: str,
        concept_drafts: list[Any],
        summary: UpsertSummary,
    ) -> dict[str, Concept]:
        concept_nodes: dict[str, Concept] = {}

        for draft in concept_drafts:
            concept = Concept(
                canonical_label=draft.canonical_label,
                category=draft.category,
                source=session.source,
            )
            validate_node(concept)
            concept.node_id = self._merge_concept(concept=concept, user_id=user_id)
            concept_nodes[concept.canonical_label] = concept
            summary.concepts_written += 1

            self._upsert_chroma_document(
                node_type="Concept",
                node_id=concept.node_id,
                user_id=user_id,
                canonical_label=concept.canonical_label,
                context_brief="",
                document=build_concept_embed_string(concept),
                source=session.source,
            )

        for draft in concept_drafts:
            if not draft.parent_concept:
                continue

            child = concept_nodes.get(draft.canonical_label)
            parent = concept_nodes.get(draft.parent_concept)
            if child is None:
                continue
            if parent is None:
                parent = Concept(
                    canonical_label=draft.parent_concept,
                    category=ConceptCategory.OTHER,
                    source=session.source,
                )
                validate_node(parent)
                parent.node_id = self._merge_concept(concept=parent, user_id=user_id)
                concept_nodes[parent.canonical_label] = parent
                summary.concepts_written += 1
                self._upsert_chroma_document(
                    node_type="Concept",
                    node_id=parent.node_id,
                    user_id=user_id,
                    canonical_label=parent.canonical_label,
                    context_brief="",
                    document=build_concept_embed_string(parent),
                    source=session.source,
                )

            self._write_edge_if_valid(
                edge=BelongsToEdge(from_node_type=NodeType.CONCEPT),
                source_node=child,
                target_node=parent,
                query="""
                // H4:EDGE_CONCEPT_BELONGS_TO
                MATCH (c:Concept {node_id: $child_id, user_id: $user_id})
                MATCH (p:Concept {node_id: $parent_id, user_id: $user_id})
                MERGE (c)-[:BELONGS_TO]->(p)
                """,
                params={"child_id": child.node_id, "parent_id": parent.node_id, "user_id": user_id},
                summary=summary,
            )

        return concept_nodes

    def _write_problem_with_solutions(
        self,
        *,
        session: Session,
        user_id: str,
        problem_output: Any,
        concept_nodes: dict[str, Concept],
        summary: UpsertSummary,
    ) -> None:
        problem = Problem(
            canonical_label=problem_output.canonical_label,
            context_brief=problem_output.context_brief,
            concepts=list(problem_output.concepts),
            severity=problem_output.severity,
            status=problem_output.status,
            symptom_keywords=list(problem_output.symptom_keywords),
            source=session.source,
        )
        validate_node(problem)

        problem_hash = content_hash("Problem", session.node_id, problem.canonical_label)
        if self._node_exists_by_content_hash(label="Problem", content_hash_value=problem_hash, user_id=user_id):
            summary.skipped_by_idempotency += 1
            return

        decision = run_dedup(problem=problem, user_id=user_id, chroma=self.collection, llm=self.llm)

        if decision.action == "MERGE" and decision.existing_node_id:
            target_problem_id = decision.existing_node_id
            self._increment_problem_recurrence(problem_id=target_problem_id, user_id=user_id)
            summary.problems_merged += 1

            merged_problem = Problem(
                node_id=target_problem_id,
                canonical_label=problem.canonical_label,
                context_brief=problem.context_brief,
                concepts=list(problem.concepts),
                severity=problem.severity,
                status=problem.status,
                symptom_keywords=list(problem.symptom_keywords),
                source=session.source,
            )
            self._write_edge_if_valid(
                edge=RecursAsEdge(recurrence_index=1),
                source_node=session,
                target_node=merged_problem,
                query="""
                // H4:EDGE_RECURS_AS
                MATCH (s:Session {node_id: $session_id, user_id: $user_id})
                MATCH (p:Problem {node_id: $problem_id, user_id: $user_id})
                MERGE (s)-[:RECURS_AS]->(p)
                """,
                params={"session_id": session.node_id, "problem_id": target_problem_id, "user_id": user_id},
                summary=summary,
            )
            problem_for_edges = merged_problem
        else:
            target_problem_id = self._create_problem(problem=problem, user_id=user_id, content_hash_value=problem_hash)
            summary.problems_created += 1

            self._upsert_chroma_document(
                node_type="Problem",
                node_id=target_problem_id,
                user_id=user_id,
                canonical_label=problem.canonical_label,
                context_brief=problem.context_brief,
                document=build_problem_embed_string(problem),
                source=session.source,
            )

            created_problem = Problem(
                node_id=target_problem_id,
                canonical_label=problem.canonical_label,
                context_brief=problem.context_brief,
                concepts=list(problem.concepts),
                severity=problem.severity,
                status=problem.status,
                symptom_keywords=list(problem.symptom_keywords),
                source=session.source,
            )
            self._write_edge_if_valid(
                edge=HasProblemEdge(),
                source_node=session,
                target_node=created_problem,
                query="""
                // H4:EDGE_HAS_PROBLEM
                MATCH (s:Session {node_id: $session_id, user_id: $user_id})
                MATCH (p:Problem {node_id: $problem_id, user_id: $user_id})
                MERGE (s)-[:HAS_PROBLEM]->(p)
                """,
                params={"session_id": session.node_id, "problem_id": target_problem_id, "user_id": user_id},
                summary=summary,
            )

            if (
                decision.action == "CREATE"
                and decision.similarity_score is not None
                and 0.50 <= decision.similarity_score <= 0.80
                and decision.existing_node_id
            ):
                related_problem = Problem(
                    node_id=decision.existing_node_id,
                    canonical_label=problem.canonical_label,
                    context_brief=problem.context_brief,
                    source=session.source,
                )
                if self._write_edge_if_valid(
                    edge=RelatedToEdge(),
                    source_node=created_problem,
                    target_node=related_problem,
                    query="""
                    // H4:EDGE_RELATED_TO
                    MATCH (a:Problem {node_id: $from_id, user_id: $user_id})
                    MATCH (b:Problem {node_id: $to_id, user_id: $user_id})
                    MERGE (a)-[:RELATED_TO]->(b)
                    """,
                    params={"from_id": target_problem_id, "to_id": decision.existing_node_id, "user_id": user_id},
                    summary=summary,
                ):
                    summary.related_to_edges_written += 1

            problem_for_edges = created_problem

        self._link_existing_solutions_to_problem(
            problem_node=problem_for_edges,
            problem_id=target_problem_id,
            user_id=user_id,
            summary=summary,
        )

        for concept_label in problem_output.concepts:
            concept = concept_nodes.get(concept_label)
            if concept is None:
                concept = Concept(canonical_label=concept_label, category=ConceptCategory.OTHER, source=session.source)
                validate_node(concept)
                concept.node_id = self._merge_concept(concept=concept, user_id=user_id)
                concept_nodes[concept_label] = concept
                summary.concepts_written += 1
                self._upsert_chroma_document(
                    node_type="Concept",
                    node_id=concept.node_id,
                    user_id=user_id,
                    canonical_label=concept.canonical_label,
                    context_brief="",
                    document=build_concept_embed_string(concept),
                    source=session.source,
                )

            self._write_edge_if_valid(
                edge=BelongsToEdge(from_node_type=NodeType.PROBLEM),
                source_node=problem_for_edges,
                target_node=concept,
                query="""
                // H4:EDGE_PROBLEM_BELONGS_TO
                MATCH (p:Problem {node_id: $problem_id, user_id: $user_id})
                MATCH (c:Concept {node_id: $concept_id, user_id: $user_id})
                MERGE (p)-[:BELONGS_TO]->(c)
                """,
                params={"problem_id": target_problem_id, "concept_id": concept.node_id, "user_id": user_id},
                summary=summary,
            )

        for solution_draft in problem_output.solutions:
            self._write_solution(
                session=session,
                user_id=user_id,
                problem_node=problem_for_edges,
                parent_problem_id=target_problem_id,
                solution_draft=solution_draft,
                summary=summary,
            )

    def _write_solution(
        self,
        *,
        session: Session,
        user_id: str,
        problem_node: Problem,
        parent_problem_id: str,
        solution_draft: Any,
        summary: UpsertSummary,
    ) -> None:
        # Promotion filter: only attempted/confirmed outcomes become graph nodes.
        if not (solution_draft.tried or solution_draft.worked is True):
            return

        solution = Solution(
            canonical_label=solution_draft.canonical_label,
            description=solution_draft.description,
            tried=solution_draft.tried,
            worked=solution_draft.worked,
            confidence=solution_draft.confidence,
            source=session.source,
        )
        validate_node(solution)

        solution_hash = content_hash("Solution", session.node_id, solution.canonical_label)
        if self._node_exists_by_content_hash(label="Solution", content_hash_value=solution_hash, user_id=user_id):
            summary.skipped_by_idempotency += 1
            return

        solution_id = self._merge_solution(
            solution=solution,
            parent_problem_id=parent_problem_id,
            user_id=user_id,
            content_hash_value=solution_hash,
        )
        summary.solutions_written += 1

        self._upsert_chroma_document(
            node_type="Solution",
            node_id=solution_id,
            user_id=user_id,
            canonical_label=solution.canonical_label,
            context_brief=solution.description,
            document=build_solution_embed_string(solution),
            parent_problem_id=parent_problem_id,
            source=session.source,
        )

        persisted_solution = Solution(
            node_id=solution_id,
            canonical_label=solution.canonical_label,
            description=solution.description,
            tried=solution.tried,
            worked=solution.worked,
            confidence=solution.confidence,
            source=session.source,
        )

        self._write_edge_if_valid(
            edge=ProposedForEdge(),
            source_node=persisted_solution,
            target_node=problem_node,
            query="""
            // H4:EDGE_PROPOSED_FOR
            MATCH (s:Solution {node_id: $solution_id, user_id: $user_id})
            MATCH (p:Problem {node_id: $problem_id, user_id: $user_id})
            MERGE (s)-[:PROPOSED_FOR]->(p)
            """,
            params={"solution_id": solution_id, "problem_id": parent_problem_id, "user_id": user_id},
            summary=summary,
        )

        if solution.worked is True:
            self._write_edge_if_valid(
                edge=ResolvedByEdge(),
                source_node=problem_node,
                target_node=persisted_solution,
                query="""
                // H4:EDGE_RESOLVED_BY
                MATCH (p:Problem {node_id: $problem_id, user_id: $user_id})
                MATCH (s:Solution {node_id: $solution_id, user_id: $user_id})
                MERGE (p)-[:RESOLVED_BY]->(s)
                """,
                params={"problem_id": parent_problem_id, "solution_id": solution_id, "user_id": user_id},
                summary=summary,
            )

    def _write_edge_if_valid(
        self,
        *,
        edge: Any,
        source_node: Any,
        target_node: Any,
        query: str,
        params: dict[str, Any],
        summary: UpsertSummary,
    ) -> bool:
        try:
            validate_edge(edge, source_node, target_node)
        except ValueError as exc:
            summary.edges_skipped += 1
            logger.warning(
                "edge_validation_failed",
                extra={
                    "edge_type": getattr(edge, "edge_type", None),
                    "source": getattr(source_node, "node_id", None),
                    "target": getattr(target_node, "node_id", None),
                    "error": str(exc),
                },
            )
            return False

        self._run_neo4j(query, **params)
        summary.edges_written += 1
        return True

    def _run_neo4j(self, query: str, **params: Any) -> Any:
        if hasattr(self.neo4j, "run"):
            return self.neo4j.run(query, **params)
        if hasattr(self.neo4j, "session"):
            with self.neo4j.session() as session:
                result = session.run(query, **params)
                if hasattr(result, "data"):
                    return result.data()
                return result
        raise ValueError("Neo4j client must expose run(...) or session().")

    def _single_record(self, result: Any) -> dict[str, Any] | None:
        if result is None:
            return None
        if isinstance(result, list):
            return result[0] if result else None
        if hasattr(result, "single"):
            record = result.single()
            if record is None:
                return None
            return dict(record)
        if hasattr(result, "data"):
            rows = result.data()
            return rows[0] if rows else None
        if isinstance(result, dict):
            return result
        return None

    def _merge_session(self, *, session: Session, user_id: str) -> str:
        result = self._run_neo4j(
            """
            // H4:MERGE_SESSION
            MERGE (s:Session {node_id: $node_id, user_id: $user_id})
            SET s.source = $source,
                s.conversation_type = $conversation_type,
                s.resolution_status = $resolution_status,
                s.title = $title,
                s.summary = $summary,
                s.message_count = $message_count,
                s.external_session_id = $external_session_id,
                s.org_id = $org_id,
                s.participants = $participants,
                s.client_name = $client_name,
                s.client_version = $client_version,
                s.source_url = $source_url,
                s.started_at = $started_at,
                s.ended_at = $ended_at,
                s.ingested_at = $ingested_at
            RETURN s.node_id AS node_id
            """,
            node_id=session.node_id,
            user_id=user_id,
            source=session.source.value,
            conversation_type=session.conversation_type.value,
            resolution_status=session.resolution_status.value,
            title=session.title,
            summary=session.summary,
            message_count=session.message_count,
            external_session_id=session.external_session_id,
            org_id=session.org_id,
            participants=list(session.participants),
            client_name=session.client_name,
            client_version=session.client_version,
            source_url=session.source_url,
            started_at=session.started_at,
            ended_at=session.ended_at,
            ingested_at=session.ingested_at,
        )
        record = self._single_record(result)
        return str((record or {}).get("node_id", session.node_id))

    def _merge_concept(self, *, concept: Concept, user_id: str) -> str:
        result = self._run_neo4j(
            """
            // H4:MERGE_CONCEPT
            MERGE (c:Concept {canonical_label: $canonical_label, user_id: $user_id})
            ON CREATE SET c.node_id = $node_id
            SET c.category = $category,
                c.source = $source,
                c.description = $description
            RETURN c.node_id AS node_id
            """,
            node_id=concept.node_id,
            canonical_label=concept.canonical_label,
            category=concept.category.value,
            source=concept.source.value,
            description=concept.description,
            user_id=user_id,
        )
        record = self._single_record(result)
        return str((record or {}).get("node_id", concept.node_id))

    def _create_problem(self, *, problem: Problem, user_id: str, content_hash_value: str) -> str:
        logger.info(f"WRITING PROBLEM: {problem.canonical_label} | {problem.context_brief}")
        result = self._run_neo4j(
            """
            // H4:CREATE_PROBLEM
            MERGE (p:Problem {node_id: $node_id, user_id: $user_id})
            SET p.canonical_label = $canonical_label,
                p.context_brief = $context_brief,
                p.severity = $severity,
                p.status = $status,
                p.symptom_keywords = $symptom_keywords,
                p.recurrence_count = coalesce(p.recurrence_count, 0),
                p.content_hash = $content_hash,
                p.source = $source
            RETURN p.node_id AS node_id
            """,
            node_id=problem.node_id,
            user_id=user_id,
            canonical_label=problem.canonical_label,
            context_brief=problem.context_brief,
            severity=problem.severity.value,
            status=problem.status.value,
            symptom_keywords=list(problem.symptom_keywords),
            content_hash=content_hash_value,
            source=problem.source.value,
        )
        record = self._single_record(result)
        return str((record or {}).get("node_id", problem.node_id))

    def _merge_solution(
        self,
        *,
        solution: Solution,
        parent_problem_id: str,
        user_id: str,
        content_hash_value: str,
    ) -> str:
        result = self._run_neo4j(
            """
            // H4:MERGE_SOLUTION
            MERGE (s:Solution {canonical_label: $canonical_label, parent_problem_id: $parent_problem_id, user_id: $user_id})
            ON CREATE SET s.node_id = $node_id
            SET s.description = $description,
                s.tried = $tried,
                s.worked = $worked,
                s.confidence = $confidence,
                s.content_hash = $content_hash,
                s.source = $source
            RETURN s.node_id AS node_id
            """,
            node_id=solution.node_id,
            canonical_label=solution.canonical_label,
            parent_problem_id=parent_problem_id,
            user_id=user_id,
            description=solution.description,
            tried=solution.tried,
            worked=solution.worked,
            confidence=solution.confidence.value,
            content_hash=content_hash_value,
            source=solution.source.value,
        )
        record = self._single_record(result)
        return str((record or {}).get("node_id", solution.node_id))

    def _increment_problem_recurrence(self, *, problem_id: str, user_id: str) -> None:
        self._run_neo4j(
            """
            // H4:INCREMENT_RECURRENCE
            MATCH (p:Problem {node_id: $problem_id, user_id: $user_id})
            SET p.recurrence_count = coalesce(p.recurrence_count, 0) + 1
            """,
            problem_id=problem_id,
            user_id=user_id,
        )

    def _node_exists_by_content_hash(self, *, label: str, content_hash_value: str, user_id: str) -> bool:
        result = self._run_neo4j(
            f"""
            // H4:CHECK_CONTENT_HASH_{label.upper()}
            MATCH (n:{label} {{content_hash: $content_hash, user_id: $user_id}})
            RETURN n.node_id AS node_id
            LIMIT 1
            """,
            content_hash=content_hash_value,
            user_id=user_id,
        )
        record = self._single_record(result)
        return bool(record and record.get("node_id"))

    def _upsert_chroma_document(
        self,
        *,
        node_type: str,
        node_id: str,
        user_id: str,
        canonical_label: str,
        context_brief: str,
        document: str,
        parent_problem_id: str | None = None,
        source: SourceType | str | None = None,
    ) -> None:
        metadata = {
            "node_type": node_type,
            "user_id": user_id,
            "neo4j_node_id": node_id,
            "canonical_label": canonical_label,
            "context_brief": context_brief,
        }
        if source is not None:
            metadata["source"] = _source_value(source)
        if parent_problem_id:
            metadata["parent_problem_id"] = parent_problem_id

        vector_id = f"{node_type.lower()}_{node_id}"

        if hasattr(self.collection, "upsert"):
            self.collection.upsert(ids=[vector_id], documents=[document], metadatas=[metadata])
            return

        if hasattr(self.collection, "add"):
            try:
                self.collection.add(ids=[vector_id], documents=[document], metadatas=[metadata])
                return
            except Exception:  # noqa: BLE001
                if hasattr(self.collection, "update"):
                    self.collection.update(ids=[vector_id], documents=[document], metadatas=[metadata])
                    return

        if hasattr(self.collection, "insert"):
            self.collection.insert(vectors=[document], payloads=[metadata], ids=[vector_id])
            return

        raise ValueError("Chroma collection must support upsert/add/update or insert.")

    def _link_existing_solutions_to_problem(
        self,
        *,
        problem_node: Problem,
        problem_id: str,
        user_id: str,
        summary: UpsertSummary,
    ) -> None:
        embed_string = build_problem_embed_string(problem_node)

        try:
            result = self.collection.query(
                query_texts=[embed_string],
                n_results=5,
                where={"node_type": "Solution", "user_id": user_id},
            )
        except Exception:  # noqa: BLE001
            return

        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]

        for node_id, distance, metadata in zip(ids, distances, metadatas):
            if not isinstance(metadata, dict):
                continue
            if metadata.get("node_type") != "Solution":
                continue

            try:
                similarity = 1.0 - float(distance)
            except Exception:  # noqa: BLE001
                continue
            if similarity < 0.70:
                continue

            existing_problem_id = str(metadata.get("parent_problem_id", ""))
            if existing_problem_id == problem_id:
                continue

            solution_node_id = str(metadata.get("neo4j_node_id") or node_id or "").strip()
            solution_label = str(metadata.get("canonical_label", "")).strip()
            solution_description = str(metadata.get("context_brief", "")).strip()
            if not solution_node_id or not solution_label or not solution_description:
                continue

            try:
                existing_solution = Solution(
                    node_id=solution_node_id,
                    canonical_label=solution_label,
                    description=solution_description,
                    source=problem_node.source,
                )
            except Exception:  # noqa: BLE001
                continue

            if self._write_edge_if_valid(
                edge=ProposedForEdge(),
                source_node=existing_solution,
                target_node=problem_node,
                query="""
                    // H4:EDGE_CROSS_SESSION_PROPOSED_FOR
                    MATCH (s:Solution {node_id: $solution_id, user_id: $user_id})
                    MATCH (p:Problem {node_id: $problem_id, user_id: $user_id})
                    MERGE (s)-[:PROPOSED_FOR]->(p)
                """,
                params={
                    "solution_id": existing_solution.node_id,
                    "problem_id": problem_id,
                    "user_id": user_id,
                },
                summary=summary,
            ):
                summary.cross_session_links_written += 1
