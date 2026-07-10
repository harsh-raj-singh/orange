from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any

from core.graph_schema_v2 import Insight, Session, SourceType, validate_node
from core.graph_upsert.dedup import get_or_create_orange_collection
from core.graph_upsert.embeddings import build_insight_embed_string

logger = logging.getLogger(__name__)
_COLLECTION_CACHE: dict[tuple[int, str], Any] = {}
_EDGE_TYPES = {"PRODUCED", "SIMILAR_TO"}


@dataclass
class UpsertSummary:
    sessions_written: int = 0
    insights_stored: int = 0
    insights_skipped: int = 0
    similar_to_edges_written: int = 0
    edges_written: int = 0
    edges_skipped: int = 0
    skipped_by_idempotency: int = 0

    # Compatibility counters kept at zero for old MCP response fields.
    concepts_written: int = 0
    problems_created: int = 0
    problems_merged: int = 0
    solutions_written: int = 0
    cross_session_links_written: int = 0
    related_to_edges_written: int = 0


def content_hash(node_type: str, session_id: str, canonical_label: str) -> str:
    raw = f"{node_type}:{session_id}:{canonical_label}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def insight_node_id_for(scope_owner: str, session_id: str, display_label: str, what: str) -> str:
    key = f"{scope_owner}:{session_id}:{display_label}:{what}"
    return f"insight_{hashlib.sha256(key.encode()).hexdigest()[:16]}"


def _source_value(source: SourceType | str) -> str:
    return source.value if isinstance(source, SourceType) else str(source)


class GraphUpsertEngine:
    """Writes completed-session ``Insight`` memory to Neo4j and Chroma."""

    def __init__(self, neo4j: Any, chroma: Any, llm: Any = None) -> None:
        self.neo4j = neo4j
        self.chroma = chroma
        self.collection: Any | None = None
        self.llm = llm

    def _collection_for_scope(self, scope: str) -> Any:
        normalized_scope = "global" if scope == "global" else "user"
        if callable(getattr(self.chroma, "query", None)):
            return self.chroma

        cache_key = (id(self.chroma), normalized_scope)
        collection = _COLLECTION_CACHE.get(cache_key)
        if collection is None:
            collection = get_or_create_orange_collection(self.chroma, scope=normalized_scope)
            _COLLECTION_CACHE[cache_key] = collection
        return collection

    def upsert_insights(
        self,
        *,
        session: Session,
        user_id: str,
        insights: list[Insight],
        scope: str = "user",
        user_email: str | None = None,
        contributed_by: str | None = None,
        org_id: str | None = None,
        company: str | None = None,
    ) -> UpsertSummary:
        summary = UpsertSummary()
        if not insights:
            return summary

        scope = "global" if scope == "global" else "user"
        identity = user_email or user_id
        self.collection = self._collection_for_scope(scope)

        validate_node(session)
        session.node_id = self._merge_session(
            session=session,
            user_id=identity if scope == "user" else "",
            scope=scope,
            user_email=user_email,
            contributed_by=contributed_by,
        )
        summary.sessions_written += 1

        for insight in insights:
            insight.scope = scope
            insight.user_id = identity if scope == "user" else None
            insight.user_email = (user_email or identity) if scope == "user" else None
            insight.org_id = org_id or session.org_id
            insight.company = company
            insight.contributed_by = contributed_by if scope == "global" else None
            insight.raw_session_id = insight.raw_session_id or session.node_id
            if not insight.node_id or insight.node_id.startswith("node_"):
                owner = (insight.org_id or "global") if scope == "global" else identity
                insight.node_id = insight_node_id_for(
                    f"{scope}:{owner}",
                    session.node_id,
                    insight.display_label,
                    insight.what,
                )
            validate_node(insight)

            similar = self._find_similar_insight(insight=insight, user_id=identity, scope=scope, org_id=insight.org_id)
            if similar and similar["node_id"] == insight.node_id:
                summary.insights_skipped += 1
                continue
            if similar and similar["similarity_score"] >= 0.95:
                self._merge_canonical_insight_update(existing_node_id=similar["node_id"], insight=insight)
                self._run_edge_direct(
                    from_id=session.node_id,
                    to_id=similar["node_id"],
                    edge_type="PRODUCED",
                    properties={"canonical_merge": True, "similarity_score": similar["similarity_score"]},
                    scope=scope,
                    summary=summary,
                )
                summary.insights_skipped += 1
                continue

            self._create_insight(insight=insight, source=session.source)
            summary.insights_stored += 1
            self._upsert_chroma_document(
                node_id=insight.node_id,
                user_id=identity,
                scope=scope,
                user_email=user_email,
                contributed_by=contributed_by,
                canonical_label=insight.display_label,
                context_brief=insight.display_summary[:180],
                document=build_insight_embed_string(insight),
                source=session.source,
                outcome=insight.outcome.value,
                tags=list(insight.tags),
                org_id=insight.org_id,
                company=insight.company,
                memory_kind=insight.memory_kind,
            )
            self._run_edge_direct(
                from_id=session.node_id,
                to_id=insight.node_id,
                edge_type="PRODUCED",
                properties={},
                scope=scope,
                summary=summary,
            )
            if similar:
                self._run_edge_direct(
                    from_id=insight.node_id,
                    to_id=similar["node_id"],
                    edge_type="SIMILAR_TO",
                    properties={"similarity_score": similar["similarity_score"]},
                    scope=scope,
                    summary=summary,
                )
                summary.similar_to_edges_written += 1

        return summary

    def _create_insight(self, *, insight: Insight, source: SourceType | str) -> str:
        self._run_neo4j(
            """
            MERGE (i:Insight {node_id: $node_id, scope: $scope})
            SET i.node_type        = 'Insight',
                i.user_id          = $user_id,
                i.user_email       = $user_email,
                i.org_id           = $org_id,
                i.company          = $company,
                i.contributed_by   = $contributed_by,
                i.memory_kind      = $memory_kind,
                i.what             = $what,
                i.why              = $why,
                i.how              = $how,
                i.outcome          = $outcome,
                i.tags             = $tags,
                i.display_label    = $display_label,
                i.display_summary  = $display_summary,
                i.raw_description  = $raw_description,
                i.raw_session_id   = $raw_session_id,
                i.source           = $source,
                i.extraction_version = $extraction_version,
                i.created_at       = coalesce(i.created_at, datetime()),
                i.updated_at       = datetime()
            RETURN i.node_id AS node_id
            """,
            node_id=insight.node_id,
            scope=insight.scope,
            user_id=insight.user_id,
            user_email=insight.user_email,
            org_id=insight.org_id,
            company=insight.company,
            contributed_by=insight.contributed_by,
            memory_kind=insight.memory_kind,
            what=insight.what,
            why=insight.why,
            how=insight.how,
            outcome=insight.outcome.value,
            tags=list(insight.tags),
            display_label=insight.display_label,
            display_summary=insight.display_summary,
            raw_description="\n".join(part for part in [insight.what, insight.why or "", insight.how or ""] if part),
            raw_session_id=insight.raw_session_id,
            source=_source_value(source),
            extraction_version=insight.extraction_version,
        )
        return insight.node_id

    def _merge_canonical_insight_update(self, *, existing_node_id: str, insight: Insight) -> None:
        self._run_neo4j(
            """
            MATCH (i:Insight {node_id: $node_id, scope: $scope})
            SET i.how = CASE
                    WHEN $how IS NULL OR trim($how) = '' THEN i.how
                    WHEN i.how IS NULL OR trim(i.how) = '' THEN $how
                    WHEN i.how CONTAINS $how THEN i.how
                    ELSE i.how + '\n' + $how
                END,
                i.outcome = CASE
                    WHEN $outcome IN ['resolved', 'partial'] THEN $outcome
                    ELSE coalesce(i.outcome, $outcome)
                END,
                i.updated_at = datetime(),
                i.canonical_merge_count = coalesce(i.canonical_merge_count, 0) + 1
            RETURN i.node_id AS node_id
            """,
            node_id=existing_node_id,
            scope=insight.scope,
            how=insight.how,
            outcome=insight.outcome.value,
        )

    def _find_similar_insight(
        self,
        *,
        insight: Insight,
        user_id: str,
        scope: str = "user",
        org_id: str | None = None,
        threshold: float = 0.88,
    ) -> dict[str, Any] | None:
        document = build_insight_embed_string(insight)
        if not document:
            return None
        if scope == "global" and not org_id:
            return None
        where = {"node_type": "Insight", "scope": "global", "org_id": org_id} if scope == "global" else {
            "node_type": "Insight",
            "scope": "user",
            "user_id": user_id,
        }
        try:
            result = self.collection.query(query_texts=[document], n_results=3, where=where)
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
            if metadata.get("node_type") != "Insight" or metadata.get("scope") != scope:
                continue
            if scope == "global" and org_id and metadata.get("org_id") != org_id:
                continue
            if scope == "user" and metadata.get("user_id") != user_id:
                continue
            try:
                similarity_score = round(1.0 - float(distance), 4)
            except Exception:  # noqa: BLE001
                continue
            if similarity_score >= threshold:
                return {
                    "node_id": str(metadata.get("neo4j_node_id") or metadata.get("node_id") or vector_id),
                    "similarity_score": similarity_score,
                }
        return None

    def _run_edge_direct(
        self,
        *,
        from_id: str,
        to_id: str,
        edge_type: str,
        properties: dict[str, Any] | None,
        scope: str,
        summary: UpsertSummary,
    ) -> None:
        normalized_edge_type = re.sub(r"[^A-Z_]", "", edge_type.upper())
        if normalized_edge_type not in _EDGE_TYPES:
            summary.edges_skipped += 1
            raise ValueError(f"Unsupported edge type: {edge_type!r}")
        self._run_neo4j(
            f"""
            MATCH (a {{node_id: $from_id}})
            MATCH (b {{node_id: $to_id}})
            MERGE (a)-[r:{normalized_edge_type}]->(b)
            SET r += $properties,
                r.scope = $scope,
                r.updated_at = datetime()
            """,
            from_id=from_id,
            to_id=to_id,
            properties=properties or {},
            scope=scope,
        )
        summary.edges_written += 1

    def _run_neo4j(self, query: str, **params: Any) -> Any:
        if hasattr(self.neo4j, "run"):
            return self.neo4j.run(query, **params)
        if hasattr(self.neo4j, "session"):
            with self.neo4j.session() as session:
                return session.run(query, **params)
        raise ValueError("Neo4j client must expose run(...) or session().")

    @staticmethod
    def _single_record(result: Any) -> dict[str, Any] | None:
        if result is None:
            return None
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

    def _merge_session(
        self,
        *,
        session: Session,
        user_id: str,
        scope: str = "user",
        user_email: str | None = None,
        contributed_by: str | None = None,
    ) -> str:
        result = self._run_neo4j(
            """
            // H4:MERGE_SESSION
            MERGE (s:Session {node_id: $node_id, scope: $scope})
            SET s.source = $source,
                s.user_id = $user_id,
                s.user_email = $user_email,
                s.contributed_by = $contributed_by,
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
                s.ingested_at = $ingested_at,
                s.created_at = coalesce(s.created_at, datetime()),
                s.updated_at = datetime()
            RETURN s.node_id AS node_id
            """,
            node_id=session.node_id,
            user_id=user_id,
            scope=scope,
            user_email=user_email,
            contributed_by=contributed_by,
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

    def _upsert_chroma_document(
        self,
        *,
        node_id: str,
        user_id: str,
        canonical_label: str,
        context_brief: str,
        document: str,
        source: SourceType | str | None = None,
        scope: str = "user",
        user_email: str | None = None,
        contributed_by: str | None = None,
        outcome: str | None = None,
        tags: list[str] | None = None,
        org_id: str | None = None,
        company: str | None = None,
        memory_kind: str | None = None,
    ) -> None:
        metadata = {
            "node_type": "Insight",
            "scope": scope,
            "node_id": node_id,
            "neo4j_node_id": node_id,
            "canonical_label": canonical_label,
            "context_brief": context_brief,
        }
        if scope == "user":
            metadata["user_id"] = user_id
            metadata["user_email"] = user_email or user_id
        if scope == "global" and contributed_by:
            metadata["contributed_by"] = contributed_by
        if org_id:
            metadata["org_id"] = org_id
        if company:
            metadata["company"] = company
        if memory_kind:
            metadata["memory_kind"] = memory_kind
        if source is not None:
            metadata["source"] = _source_value(source)
        if outcome:
            metadata["outcome"] = outcome
        if tags is not None:
            metadata["tags"] = ",".join(tags)

        vector_id = f"insight_{node_id}"
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
