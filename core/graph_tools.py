from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.graph_schema import (
    GraphNode,
    LEVEL_SESSION,
    RELATIONSHIP_TYPES,
    SESSION_INTENTS,
)


WRITE_SESSION_GRAPH_TOOL = {
    "name": "write_session_graph",
    "description": "Write validated session graph nodes and relationships for one completed chat.",
    "parameters": {
        "type": "object",
        "properties": {
            "nodes": {"type": "array", "items": {"type": "object"}},
            "relationships": {"type": "array", "items": {"type": "object"}},
            "chat_id": {"type": "string"},
            "user_id": {"type": "string"},
        },
        "required": ["nodes", "relationships", "chat_id", "user_id"],
    },
}

FETCH_NODE_WITH_NEIGHBORS_TOOL = {
    "name": "fetch_node_with_neighbors",
    "description": "Fetch one node and up to 5 immediate neighbors, optionally filtered by relation/outcome.",
    "parameters": {
        "type": "object",
        "properties": {
            "node_id": {"type": "string"},
            "max_neighbors": {"type": "integer", "minimum": 1, "maximum": 5},
            "relation_filter": {"type": "array", "items": {"type": "string"}},
            "outcome_filter": {"type": "string", "enum": ["worked", "failed", "partial"]},
            "user_id": {"type": "string"},
        },
        "required": ["node_id", "max_neighbors", "user_id"],
    },
}

SEARCH_AND_FETCH_TOOL = {
    "name": "search_and_fetch",
    "description": "Run semantic node search and fetch 1-hop neighbors for top matches.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 3},
            "max_neighbors": {"type": "integer", "minimum": 1, "maximum": 5},
            "outcome_filter": {"type": "string", "enum": ["worked", "failed", "partial"]},
            "intent_filter": {"type": "string", "enum": SESSION_INTENTS},
            "current_node_id": {"type": "string"},
            "user_id": {"type": "string"},
        },
        "required": ["query", "top_k", "max_neighbors", "user_id"],
    },
}


class GraphTools:
    def __init__(self, graph_driver, graph_merger, vector_store, embedding_model, logger=None):
        self.graph_driver = graph_driver
        self.graph_merger = graph_merger
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self.logger = logger

    def _log(self, event: str, **kwargs: Any) -> None:
        if self.logger:
            self.logger.info(event, extra=kwargs)

    def _hash_user_id(self, user_id: str) -> str:
        return hashlib.sha256((user_id or "").encode("utf-8")).hexdigest()[:24]

    def _create_edge_by_id(self, source_id: str, relation: str, target_id: str, user_id: str) -> None:
        if relation not in RELATIONSHIP_TYPES or not self.graph_driver:
            return
        query = f"""
        MATCH (a {{id: $source_id, user_id: $user_id}})
        MATCH (b {{id: $target_id, user_id: $user_id}})
        MERGE (a)-[r:{relation}]->(b)
        ON CREATE SET r.created_at = $now
        SET r.updated_at = $now
        """
        with self.graph_driver.session() as session:
            session.run(
                query,
                source_id=source_id,
                target_id=target_id,
                user_id=user_id,
                now=datetime.now(timezone.utc).isoformat(),
            )

    def _update_node_metadata(self, node_id: str, user_id: str, node: GraphNode) -> None:
        if not self.graph_driver:
            return
        with self.graph_driver.session() as session:
            session.run(
                """
                MATCH (n {id: $node_id, user_id: $user_id})
                SET n.session_intent = $session_intent,
                    n.display_name = $display_name,
                    n.source_type = $source_type,
                    n.extraction_version = $extraction_version,
                    n.outcome = $outcome,
                    n.importance =
                        CASE
                            WHEN n.importance < $importance THEN $importance
                            ELSE n.importance
                        END,
                    n.user_ids =
                        CASE
                            WHEN $user_id IN coalesce(n.user_ids, []) THEN coalesce(n.user_ids, [])
                            ELSE coalesce(n.user_ids, []) + [$user_id]
                        END,
                    n.updated_at = $now
                """,
                node_id=node_id,
                user_id=user_id,
                session_intent=node.session_intent,
                display_name=node.display_name or node.name,
                source_type=node.source_type,
                extraction_version=node.extraction_version,
                outcome=node.outcome or "unknown",
                importance=max(0.0, min(1.0, float(node.importance))),
                now=datetime.now(timezone.utc).isoformat(),
            )

    def _upsert_node_vector(self, node_id: str, node: GraphNode, chat_id: str, user_id: str, embedding: List[float]) -> str:
        vector_id = f"nodevec_{node_id}"
        payload = {
            "node_id": node_id,
            "node_type": node.node_type,
            "session_intent": node.session_intent,
            "outcome": node.outcome or "unknown",
            "chat_id": chat_id,
            "user_id": self._hash_user_id(user_id),
            "importance": max(0.0, min(1.0, float(node.importance))),
            "created_at": node.created_at.isoformat(),
        }
        try:
            self.vector_store.insert([embedding], [payload], [vector_id])
        except Exception:
            self.vector_store.update(vector_id, vector=embedding, payload=payload)
        return vector_id

    def write_session_graph(
        self,
        nodes: List[GraphNode],
        relationships: List[Dict[str, str]],
        chat_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        validated_nodes: List[GraphNode] = []
        for raw in nodes:
            try:
                node = raw if isinstance(raw, GraphNode) else GraphNode(**raw)
                validated_nodes.append(node)
            except Exception:
                self._log("drop_invalid_node", chat_id=chat_id)

        session_node = next((n for n in validated_nodes if n.node_type == "session"), None)
        if session_node is None:
            session_node = GraphNode(
                id=str(uuid4()),
                name=f"Session {chat_id[:8]}",
                display_name=f"Session {chat_id[:8]}",
                node_type="session",
                level=LEVEL_SESSION,
                context="Root node for this chat session.",
                session_intent="general",
                source_type="chat",
                chat_ids=[chat_id],
                vector_refs=[],
                user_ids=[user_id],
                embedding=None,
                mention_count=1,
                importance=0.6,
                outcome="unknown",
                extraction_version="dspy_v1",
            )
            validated_nodes.insert(0, session_node)

        names = [n.name for n in validated_nodes]
        embedding_map = self.graph_merger.batch_embed_names(names) if names else {}

        node_map: Dict[str, str] = {}
        name_to_input_id: Dict[str, str] = {n.name: n.id for n in validated_nodes}
        persisted_ids: List[str] = []

        def _persist(node: GraphNode) -> str:
            graph_id, _ = self.graph_merger.find_or_create_node(
                {
                    "name": node.name,
                    "display_name": node.display_name,
                    "type": node.node_type,
                    "level": node.level,
                    "context": node.context,
                },
                user_id,
                chat_id,
                f"nodevec_{node.id}",
                precomputed_embedding=embedding_map.get(node.name),
            )
            node_map[node.id] = graph_id
            persisted_ids.append(graph_id)
            self._update_node_metadata(graph_id, user_id, node)
            node_embedding = embedding_map.get(node.name) or self.embedding_model.embed(f"{node.name}\n{node.context}")
            self._upsert_node_vector(graph_id, node, chat_id, user_id, node_embedding)
            return graph_id

        session_graph_id = _persist(session_node)
        for node in validated_nodes:
            if node.id == session_node.id:
                continue
            _persist(node)

        for node in validated_nodes:
            if node.id == session_node.id:
                continue
            self._create_edge_by_id(node_map[node.id], "PART_OF", session_graph_id, user_id)

        for rel in relationships:
            relation = str(rel.get("relation", "")).strip()
            if relation not in RELATIONSHIP_TYPES:
                self._log("drop_invalid_relation", relation=relation, chat_id=chat_id)
                continue
            source_ref = str(rel.get("source_id") or rel.get("source") or "").strip()
            target_ref = str(rel.get("target_id") or rel.get("target") or "").strip()
            if source_ref not in node_map:
                source_ref = name_to_input_id.get(source_ref, "")
            if target_ref not in node_map:
                target_ref = name_to_input_id.get(target_ref, "")
            source_id = node_map.get(source_ref)
            target_id = node_map.get(target_ref)
            if not source_id or not target_id:
                self._log("drop_unresolved_relation", chat_id=chat_id, relation=relation)
                continue
            self._create_edge_by_id(source_id, relation, target_id, user_id)

        return {
            "status": "ok",
            "node_ids": persisted_ids,
            "session_node_id": session_graph_id,
            "node_count": len(persisted_ids),
        }

    def fetch_node_with_neighbors(
        self,
        node_id: str,
        max_neighbors: int,
        relation_filter: Optional[List[str]] = None,
        outcome_filter: Optional[str] = None,
        user_id: str = "",
    ) -> Dict[str, Any]:
        if not self.graph_driver:
            return {"node": None, "neighbors": []}

        max_neighbors = max(1, min(5, int(max_neighbors)))
        relation_filter = [r for r in (relation_filter or []) if r in RELATIONSHIP_TYPES]
        outcome_filter = outcome_filter if outcome_filter in {"worked", "failed", "partial"} else None

        with self.graph_driver.session() as session:
            node_row = session.run(
                """
                MATCH (n {id: $node_id, user_id: $user_id})
                RETURN n
                """,
                node_id=node_id,
                user_id=user_id,
            ).single()
            if not node_row:
                return {"node": None, "neighbors": []}

            rel_where = ""
            params: Dict[str, Any] = {
                "node_id": node_id,
                "user_id": user_id,
                "max_neighbors": max_neighbors,
            }
            if relation_filter:
                rel_where += " AND type(r) IN $relation_filter"
                params["relation_filter"] = relation_filter
            if outcome_filter:
                rel_where += " AND coalesce(target.outcome, 'unknown') = $outcome_filter"
                params["outcome_filter"] = outcome_filter

            neighbors = session.run(
                f"""
                MATCH (source {{id: $node_id, user_id: $user_id}})-[r]->(target {{user_id: $user_id}})
                WHERE 1=1 {rel_where}
                RETURN source.id AS source_id, source.name AS source_name, type(r) AS relationship, target
                LIMIT $max_neighbors
                """,
                **params,
            ).data()

        flat_neighbors = []
        for row in neighbors:
            target = dict(row["target"])
            flat_neighbors.append(
                {
                    "source_id": row["source_id"],
                    "source_name": row["source_name"],
                    "relationship": row["relationship"],
                    "target": target,
                }
            )
        return {"node": dict(node_row["n"]), "neighbors": flat_neighbors}

    def get_graph_for_chat(self, chat_id: str, user_id: str) -> Dict[str, Any]:
        if not self.graph_driver:
            return {"nodes": [], "edges": []}

        query = """
        MATCH (n {user_id: $user_id})
        WHERE $chat_id IN coalesce(n.chat_ids, [])
        WITH collect(n) AS scoped_nodes, collect(n.id) AS scoped_ids

        UNWIND scoped_nodes AS src
        OPTIONAL MATCH (src)-[r]->(dst)
        WHERE dst IN scoped_nodes

        WITH scoped_nodes, scoped_ids,
             collect(
                 CASE WHEN r IS NULL THEN NULL
                 ELSE {source_id: src.id, relation: type(r), target_id: dst.id, properties: properties(r)}
                 END
             ) AS internal_rels

        UNWIND scoped_nodes AS src2
        OPTIONAL MATCH (src2)-[cr:RELATED_TO]->(cross_dst)
        WHERE cr.cross_chat = true AND NOT cross_dst.id IN scoped_ids

        WITH scoped_nodes, internal_rels,
             collect(cross_dst) AS cross_nodes,
             collect(
                 CASE WHEN cr IS NULL THEN NULL
                 ELSE {source_id: src2.id, relation: type(cr), target_id: cross_dst.id, properties: properties(cr)}
                 END
             ) AS cross_rels

        RETURN
            [node IN scoped_nodes | properties(node)] +
            [node IN cross_nodes | properties(node)] AS nodes,
            [rel IN internal_rels WHERE rel IS NOT NULL] +
            [rel IN cross_rels WHERE rel IS NOT NULL] AS edges
        """

        with self.graph_driver.session() as session:
            row = session.run(query, chat_id=chat_id, user_id=user_id).single()
            if not row:
                return {"nodes": [], "edges": []}
            return {
                "nodes": row["nodes"] or [],
                "edges": row["edges"] or [],
            }

    def _write_cross_chat_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        relation: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.graph_driver:
            return
        if not source_node_id or not target_node_id or source_node_id == target_node_id:
            return

        reason = str((metadata or {}).get("reason", "retrieval_match"))
        now = datetime.now(timezone.utc).isoformat()
        query = """
        MATCH (a {id: $source_id}), (b {id: $target_id})
        MERGE (a)-[r:RELATED_TO]->(b)
        ON CREATE SET r.created_at = $now, r.reason = $reason, r.cross_chat = true
        ON MATCH SET r.updated_at = $now, r.hit_count = coalesce(r.hit_count, 0) + 1
        """
        with self.graph_driver.session() as session:
            session.run(
                query,
                source_id=source_node_id,
                target_id=target_node_id,
                now=now,
                reason=reason,
            )

    def search_and_fetch(
        self,
        query: str,
        top_k: int,
        max_neighbors: int,
        outcome_filter: Optional[str] = None,
        intent_filter: Optional[str] = None,
        current_node_id: Optional[str] = None,
        user_id: str = "",
        retrieval_threshold: float = 0.75,
    ) -> Dict[str, Any]:
        top_k = max(1, min(3, int(top_k)))
        max_neighbors = max(1, min(5, int(max_neighbors)))
        if intent_filter not in SESSION_INTENTS:
            intent_filter = None
        if outcome_filter not in {"worked", "failed", "partial"}:
            outcome_filter = None

        query_embedding = self.embedding_model.embed(query)
        filters = {"user_id": self._hash_user_id(user_id)}
        if intent_filter:
            filters["session_intent"] = intent_filter
        if outcome_filter:
            filters["outcome"] = outcome_filter

        hits = self.vector_store.search(
            query="",
            vectors=[query_embedding],
            limit=top_k,
            filters=filters,
        )

        context_entries = []
        for hit in hits:
            score = float(getattr(hit, "score", 0.0))
            if score < float(retrieval_threshold):
                continue
            payload = hit.payload if hasattr(hit, "payload") else {}
            node_id = payload.get("node_id") if isinstance(payload, dict) else None
            if not node_id:
                continue
            if current_node_id:
                self._write_cross_chat_edge(
                    source_node_id=str(current_node_id),
                    target_node_id=str(node_id),
                    relation="RELATED_TO",
                    metadata={"reason": "retrieval_match"},
                )
            context_entries.append(
                {
                    "score": score,
                    "match": payload,
                    "graph": self.fetch_node_with_neighbors(
                        node_id=node_id,
                        max_neighbors=max_neighbors,
                        relation_filter=[],
                        outcome_filter=outcome_filter,
                        user_id=user_id,
                    ),
                }
            )

        return {
            "query": query,
            "matches": context_entries,
            "count": len(context_entries),
        }
