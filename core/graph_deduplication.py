"""
🔍 GRAPH DUPLICATION DETECTION & INTELLIGENT MERGING
====================================================

Challenge: How to quickly check if a concept already exists in the graph?

Solution: Multi-stage fuzzy matching with embedding-based similarity
"""

import json
import re
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
from neo4j.exceptions import ServiceUnavailable, SessionExpired, TransientError


logger = logging.getLogger(__name__)
RETRYABLE_NEO4J_ERRORS = (ServiceUnavailable, SessionExpired, TransientError, OSError)


def _strip_json_fence(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    return cleaned


def _safe_json_loads(text: str, fallback: Any) -> Any:
    try:
        return json.loads(_strip_json_fence(text))
    except Exception:
        return fallback


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


@dataclass
class GraphNode:
    """Standardized graph node structure"""
    id: str
    name: str
    display_name: str
    type: str  # concept, problem, solution
    level: int  # 1, 2, 3
    context: str
    embedding: Optional[List[float]] = None
    chat_ids: List[str] = None
    vector_refs: List[str] = None
    mention_count: int = 0
    importance: float = 0.5


class IntelligentGraphMerger:
    """
    Handles duplicate detection and intelligent node merging
    
    Strategy:
    1. Quick hash-based exact match (O(1))
    2. Fuzzy string matching on names (O(n))
    3. Embedding similarity (O(n) but only for close matches)
    4. LLM-based semantic comparison (only for edge cases)
    """
    
    def __init__(self, graph_driver, embedding_model, llm):
        self.graph_driver = graph_driver
        self.embedding_model = embedding_model
        self.llm = llm
        
        # In-memory cache for fast lookups
        self.node_cache = {}  # {user_id: {node_hash: node_id}}
        self._build_cache()

    def _run_neo4j(
        self,
        query: str,
        params: Dict[str, Any],
        *,
        fetch: str = "none",
        attempts: int = 3,
    ) -> Any:
        """Run Neo4j query with retry for transient connection failures."""
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                with self.graph_driver.session() as session:
                    result = session.run(query, **params)
                    if fetch == "single":
                        return result.single()
                    if fetch == "data":
                        return result.data()
                    result.consume()
                    return None
            except RETRYABLE_NEO4J_ERRORS as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                logger.warning(
                    "neo4j_transient_retry",
                    extra={"attempt": attempt, "max_attempts": attempts, "error": str(exc)},
                )
                time.sleep(0.25 * attempt)
        if last_error:
            raise last_error
        return None
    
    def batch_embed_names(self, names: List[str]) -> Dict[str, List[float]]:
        """
        Pre-compute embeddings for a batch of names.
        
        This is much more efficient than embedding one at a time.
        Returns a dict mapping name -> embedding.
        """
        if not names:
            return {}
        
        # Remove duplicates while preserving order
        unique_names = list(dict.fromkeys(names))
        
        # Batch embed all names at once
        embeddings = self.embedding_model.embed(unique_names)
        
        # Handle case where embed() returns a single list for single input
        if unique_names and not isinstance(embeddings[0], list):
            embeddings = [embeddings]
        
        return dict(zip(unique_names, embeddings))
    
    def _build_cache(self):
        """
        Build in-memory index of all nodes for fast lookup
        
        This runs once at startup and is updated as nodes are added
        """
        query = """
        MATCH (n)
        RETURN n.id as id, 
               n.name as name, 
               n.display_name as display_name,
               n.type as type,
               n.user_id as user_id,
               n.embedding as embedding
        """
        
        results = self._run_neo4j(query, {}, fetch="data") or []

        for record in results:
            user_id = record["user_id"]
            node_name = record["name"]
            node_type = record["type"]
            if not user_id:
                continue
            if not isinstance(node_name, str) or not node_name.strip():
                continue
            if not isinstance(node_type, str) or not node_type.strip():
                node_type = "unknown"
            
            if user_id not in self.node_cache:
                self.node_cache[user_id] = {}
            
            # Create hash for exact match
            node_hash = self._hash_node(node_name, node_type)
            self.node_cache[user_id][node_hash] = {
                "id": record["id"],
                "name": node_name,
                "display_name": record.get("display_name") or node_name,
                "type": node_type,
                "embedding": record.get("embedding")
            }
    
    def _hash_node(self, name: str, node_type: str) -> str:
        """
        Create deterministic hash for exact matching
        
        Normalizations:
        - Lowercase
        - Remove extra whitespace
        - Remove special characters
        """
        normalized = (name or "").lower().strip()
        normalized = " ".join(normalized.split())  # Collapse whitespace
        hash_input = f"{normalized}::{(node_type or 'unknown').strip() or 'unknown'}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    def find_or_create_node(
        self,
        node_data: Dict[str, Any],
        user_id: str,
        chat_id: str,
        vector_id: str,
        precomputed_embedding: Optional[List[float]] = None
    ) -> Tuple[str, bool]:
        """
        Find existing node or create new one
        
        Args:
            node_data: {
                "name": "AWS S3",
                "type": "concept",
                "level": 1,
                "context": "Amazon S3 storage service"
            }
            user_id: User ID
            chat_id: Current chat ID
            vector_id: Vector DB reference
        
        Returns:
            (node_id, was_created)
            - If existing: (existing_id, False)
            - If new: (new_id, True)
        
        Note:
            Pass precomputed_embedding to avoid redundant embedding calls
            when processing multiple nodes in batch.
        """
        
        # Stage 1: Exact hash match (fastest)
        node_hash = self._hash_node(node_data["name"], node_data["type"])
        
        if user_id in self.node_cache:
            if node_hash in self.node_cache[user_id]:
                # Exact match found!
                existing_node = self.node_cache[user_id][node_hash]
                
                # Update existing node with new chat reference
                self._add_chat_reference(
                    existing_node["id"],
                    chat_id,
                    vector_id,
                    user_id,
                    node_data.get("display_name") or node_data["name"]
                )
                
                return existing_node["id"], False
        
        # Stage 2: Fuzzy name matching
        similar_node = self._find_similar_by_name(
            node_data["name"],
            node_data["type"],
            user_id,
            threshold=0.85,
            query_embedding=precomputed_embedding
        )
        
        if similar_node:
            # Found similar node - ask LLM if they're the same
            are_same = self._llm_check_equivalence(
                node_data["name"],
                similar_node["name"],
                node_data.get("context", ""),
                similar_node.get("context", "")
            )
            
            if are_same:
                # Merge with similar node
                self._add_chat_reference(
                    similar_node["id"],
                    chat_id,
                    vector_id,
                    user_id,
                    node_data.get("display_name") or node_data["name"]
                )
                
                # Update cache
                if user_id not in self.node_cache:
                    self.node_cache[user_id] = {}
                self.node_cache[user_id][node_hash] = similar_node
                
                return similar_node["id"], False
        
        # Stage 3: No match - create new node
        new_node_id = self._create_new_node(
            node_data,
            user_id,
            chat_id,
            vector_id
        )
        
        # Update cache
        if user_id not in self.node_cache:
            self.node_cache[user_id] = {}
        
        # Use precomputed embedding or compute one for future similarity checks
        embedding = precomputed_embedding or self.embedding_model.embed(node_data["name"])
        
        self.node_cache[user_id][node_hash] = {
            "id": new_node_id,
            "name": node_data["name"],
            "display_name": node_data.get("display_name") or node_data["name"],
            "type": node_data["type"],
            "embedding": embedding
        }
        
        # Also store embedding in graph
        self._update_node_embedding(new_node_id, embedding, user_id)
        
        return new_node_id, True
    
    def _find_similar_by_name(
        self,
        name: str,
        node_type: str,
        user_id: str,
        threshold: float = 0.85,
        query_embedding: Optional[List[float]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Find similar node using fuzzy string matching + embeddings
        
        This is the key to avoiding "AWS S3" vs "S3" vs "Amazon S3" duplicates
        """
        
        if user_id not in self.node_cache:
            return None
        
        # Get all nodes of same type
        candidates = [
            node for node in self.node_cache[user_id].values()
            if node["type"] == node_type
        ]
        
        if not candidates:
            return None
        
        # Use precomputed embedding or compute query embedding
        if query_embedding is None:
            query_embedding = self.embedding_model.embed(name)
        
        best_match = None
        best_score = 0.0
        
        for candidate in candidates:
            # 1. String similarity (Levenshtein ratio)
            from difflib import SequenceMatcher
            string_sim = SequenceMatcher(
                None,
                name.lower(),
                candidate["name"].lower()
            ).ratio()
            
            # 2. Embedding similarity (cosine)
            if candidate.get("embedding"):
                emb_sim = self._cosine_similarity(
                    query_embedding,
                    candidate["embedding"]
                )
            else:
                emb_sim = 0.0
            
            # Combined score (60% embedding, 40% string)
            # Embedding is more important as it captures semantic meaning
            combined_score = 0.6 * emb_sim + 0.4 * string_sim
            
            if combined_score > best_score:
                best_score = combined_score
                best_match = candidate
        
        if best_score >= threshold:
            # Get full node details from graph
            return self._get_full_node(best_match["id"], user_id)
        
        return None
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors"""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        
        dot_product = np.dot(vec1, vec2)
        norm_product = np.linalg.norm(vec1) * np.linalg.norm(vec2)
        
        if norm_product == 0:
            return 0.0
        
        return dot_product / norm_product
    
    def _llm_check_equivalence(
        self,
        name1: str,
        name2: str,
        context1: str,
        context2: str
    ) -> bool:
        """
        Use LLM to decide if two similar nodes are actually the same
        
        This is the final arbiter for edge cases
        """
        
        prompt = f"""
Are these two concepts referring to the same thing?

Concept 1:
Name: {name1}
Context: {context1}

Concept 2:
Name: {name2}
Context: {context2}

Consider:
- Are they synonyms? (e.g., "AWS S3" = "Amazon S3" = "S3")
- Are they the same level of abstraction?
- Do they refer to the same entity?

Return JSON:
{{
  "are_same": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}

Examples:
- "AWS S3" vs "Amazon S3" → true (synonyms)
- "S3" vs "AWS S3" → true (same entity)
- "S3 Permissions" vs "S3" → false (different level)
- "S3 403 Error" vs "S3 404 Error" → false (different problems)
"""
        
        response = self.llm.generate_response(
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse response
        import json
        try:
            data = json.loads(response.strip())
            return data.get("are_same", False) and data.get("confidence", 0.0) >= 0.8
        except:
            # Fallback: conservative - don't merge
            return False
    
    def _get_full_node(self, node_id: str, user_id: str) -> Dict[str, Any]:
        """Fetch full node details from graph"""
        
        query = """
        MATCH (n {id: $node_id, user_id: $user_id})
        RETURN n
        """
        
        record = self._run_neo4j(
            query,
            {"node_id": node_id, "user_id": user_id},
            fetch="single",
        )
        if record:
            return dict(record["n"])
        
        return None
    
    def _add_chat_reference(
        self,
        node_id: str,
        chat_id: str,
        vector_id: str,
        user_id: str,
        display_name: str
    ):
        """
        Update existing node with new chat reference
        
        Increments:
        - mention_count
        - chat_ids list
        - vector_refs list
        """
        
        query = """
        MATCH (n {id: $node_id, user_id: $user_id})
        SET n.chat_ids = 
            CASE 
                WHEN $chat_id IN n.chat_ids THEN n.chat_ids
                ELSE n.chat_ids + [$chat_id]
            END,
            n.vector_refs = 
            CASE
                WHEN $vector_id IN n.vector_refs THEN n.vector_refs
                ELSE n.vector_refs + [$vector_id]
            END,
            n.mention_count = n.mention_count + 1,
            n.updated_at = $now,
            n.display_name = CASE
                WHEN trim(coalesce(n.display_name, '')) = '' THEN $display_name
                ELSE n.display_name
            END,
            n.importance = n.importance + 0.05  # Boost importance with each mention
        RETURN n
        """
        
        self._run_neo4j(
            query,
            {
                "node_id": node_id,
                "user_id": user_id,
                "chat_id": chat_id,
                "vector_id": vector_id,
                "display_name": display_name,
                "now": datetime.now(timezone.utc).isoformat(),
            },
        )
    
    def _create_new_node(
        self,
        node_data: Dict[str, Any],
        user_id: str,
        chat_id: str,
        vector_id: str
    ) -> str:
        """Create new node in graph"""
        
        import uuid
        node_id = f"{node_data['type']}_{uuid.uuid4().hex[:8]}"
        
        # Determine node label based on type
        label_map = {
            "concept": "Concept",
            "service": "Service",
            "tool": "Tool",
            "technology": "Technology",
            "problem": "Problem",
            "solution": "Solution",
            "session": "Session",
            "attempt": "Attempt",
            "context": "Context",
            "decision": "Decision",
            "open_question": "OpenQuestion",
            "artifact": "Artifact",
            "domain": "Domain",
            "subject": "Subject",
            "topic": "Topic",
            "method": "Method",
        }
        label = label_map.get(node_data["type"], "Concept")
        
        query = f"""
        CREATE (n:{label} {{
            id: $id,
            name: $name,
            display_name: $display_name,
            type: $type,
            level: $level,
            context: $context,
            chat_ids: [$chat_id],
            vector_refs: [$vector_id],
            user_id: $user_id,
            created_at: $now,
            updated_at: $now,
            mention_count: 1,
            importance: 0.5
        }})
        RETURN n.id as id
        """
        
        record = self._run_neo4j(
            query,
            {
                "id": node_id,
                "name": node_data["name"],
                "display_name": node_data.get("display_name") or node_data["name"],
                "type": node_data["type"],
                "level": node_data.get("level", 1),
                "context": node_data.get("context", ""),
                "chat_id": chat_id,
                "vector_id": vector_id,
                "user_id": user_id,
                "now": datetime.now(timezone.utc).isoformat(),
            },
            fetch="single",
        )
        return record["id"] if record else node_id
    
    def _update_node_embedding(
        self,
        node_id: str,
        embedding: List[float],
        user_id: str
    ):
        """Store embedding in graph node for future similarity checks"""
        
        query = """
        MATCH (n {id: $node_id, user_id: $user_id})
        SET n.embedding = $embedding
        """
        
        self._run_neo4j(
            query,
            {"node_id": node_id, "user_id": user_id, "embedding": embedding},
        )


# ================================================================
# USAGE EXAMPLE
# ================================================================

"""
merger = IntelligentGraphMerger(graph_driver, embedding_model, llm)

# Scenario 1: First mention of AWS S3
node_id_1, created = merger.find_or_create_node(
    node_data={
        "name": "AWS S3",
        "type": "service",
        "level": 1,
        "context": "Amazon S3 object storage"
    },
    user_id="user_123",
    chat_id="chat_abc",
    vector_id="vec_abc"
)
# Result: (node_id_1, True) - new node created

# Scenario 2: Later chat mentions "Amazon S3"
node_id_2, created = merger.find_or_create_node(
    node_data={
        "name": "Amazon S3",
        "type": "service",
        "level": 1,
        "context": "AWS object storage service"
    },
    user_id="user_123",
    chat_id="chat_def",
    vector_id="vec_def"
)
# Result: (node_id_1, False) - same node, merged!
# LLM determined "AWS S3" == "Amazon S3"

# Scenario 3: Chat mentions "S3 Permissions" (different concept)
node_id_3, created = merger.find_or_create_node(
    node_data={
        "name": "S3 Permissions",
        "type": "concept",
        "level": 2,
        "context": "Access control for S3 buckets"
    },
    user_id="user_123",
    chat_id="chat_ghi",
    vector_id="vec_ghi"
)
# Result: (node_id_3, True) - different node, created
# Different level and context, so NOT merged with "AWS S3"
"""


# ================================================================
# GRAPH TRAVERSAL WITH NODE IDS
# ================================================================

class AgenticGraphTraversalByID:
    """
    Modified agentic traversal that works with node IDs instead of names
    
    This is more efficient since we already have IDs from vector search
    """
    
    def __init__(self, graph_driver, llm, max_depth: int = 3):
        self.graph_driver = graph_driver
        self.llm = llm
        self.max_depth = max_depth
    
    def traverse_for_query_by_ids(
        self,
        query: str,
        starting_node_ids: List[str],
        user_id: str,
        max_context_size: int = 2000
    ) -> Dict[str, Any]:
        """
        Start traversal from specific node IDs (not names)
        
        This is called from retrieval when we already have node IDs
        from vector search payloads
        """
        
        if not starting_node_ids:
            return self._empty_result()
        
        context = {
            "nodes": [],
            "relationships": [],
            "visited": set(),
            "reasoning_trace": []
        }
        
        # Fetch starting nodes
        starting_nodes = self._get_nodes_by_ids(starting_node_ids, user_id)
        if not starting_nodes:
            return self._empty_result()
        
        current_layer_ids = [n["id"] for n in starting_nodes]
        context["nodes"].extend(starting_nodes)
        context["visited"].update(current_layer_ids)
        
        depth = 0
        
        while depth < self.max_depth and current_layer_ids:
            # Get neighbors
            neighbors = self._get_neighbors_by_ids(current_layer_ids, user_id)
            
            if not neighbors:
                context["reasoning_trace"].append(
                    f"Depth {depth}: No more neighbors. Stopping."
                )
                break
            
            # Ask LLM which paths to follow
            decision = self._llm_decide_traversal(
                query=query,
                current_nodes=context["nodes"][-len(current_layer_ids):],
                neighbors=neighbors,
                context_so_far=context,
                depth=depth
            )
            
            if decision["action"] == "STOP":
                context["reasoning_trace"].append(
                    f"Depth {depth}: LLM decided to stop. {decision.get('reasoning', '')}"
                )
                break
            
            # Add selected nodes
            selected_nodes = decision.get("selected_nodes", [])
            new_layer_ids = []
            
            for node in selected_nodes:
                if node["id"] not in context["visited"]:
                    context["nodes"].append(node)
                    context["visited"].add(node["id"])
                    new_layer_ids.append(node["id"])
            
            # Add relationships
            context["relationships"].extend(
                decision.get("selected_relationships", [])
            )
            
            context["reasoning_trace"].append(
                f"Depth {depth}: Explored {len(selected_nodes)} nodes - {decision.get('reasoning', '')}"
            )
            
            current_layer_ids = new_layer_ids
            depth += 1
            
            # Check size
            if self._estimate_size(context) > max_context_size:
                context["reasoning_trace"].append("Context size limit reached.")
                break
        
        context["depth_reached"] = depth
        context["total_nodes"] = len(context["nodes"])
        del context["visited"]
        
        return context
    
    def _get_nodes_by_ids(
        self,
        node_ids: List[str],
        user_id: str
    ) -> List[Dict[str, Any]]:
        """Fetch nodes by their IDs"""
        
        query = """
        MATCH (n {user_id: $user_id})
        WHERE n.id IN $node_ids
        RETURN n
        """
        
        with self.graph_driver.session() as session:
            results = session.run(query, node_ids=node_ids, user_id=user_id)
            return [dict(r["n"]) for r in results]
    
    def _get_neighbors_by_ids(
        self,
        node_ids: List[str],
        user_id: str
    ) -> List[Dict[str, Any]]:
        """Get neighbors of specific node IDs"""
        
        query = """
        MATCH (source {user_id: $user_id})
        WHERE source.id IN $node_ids
        MATCH (source)-[r]->(target {user_id: $user_id})
        RETURN 
            source.id AS source_id,
            source.name AS source_name,
            type(r) AS relationship,
            target.id AS target_id,
            target.name AS target_name,
            target.type AS target_type,
            target.level AS target_level,
            target.context AS target_context
        LIMIT 50
        """
        
        with self.graph_driver.session() as session:
            results = session.run(query, node_ids=node_ids, user_id=user_id)
            
            neighbors = []
            for record in results:
                neighbors.append({
                    "source_id": record["source_id"],
                    "source_name": record["source_name"],
                    "relationship": record["relationship"],
                    "target": {
                        "id": record["target_id"],
                        "name": record["target_name"],
                        "type": record["target_type"],
                        "level": record["target_level"],
                        "context": record["target_context"]
                    }
                })
            
            return neighbors

    def _format_nodes(self, nodes: List[Dict[str, Any]]) -> str:
        if not nodes:
            return "None"
        lines = []
        for node in nodes:
            lines.append(
                f"- {node.get('name')} (type={node.get('type')}, level={node.get('level')}) "
                f"{node.get('context', '')}"
            )
        return "\n".join(lines)

    def _format_neighbors(self, neighbors: List[Dict[str, Any]]) -> str:
        if not neighbors:
            return "None"
        lines = []
        for idx, neighbor in enumerate(neighbors):
            target = neighbor["target"]
            lines.append(
                f"{idx}. {neighbor.get('source_name')} -[{neighbor.get('relationship')}]-> "
                f"{target.get('name')} (type={target.get('type')}, level={target.get('level')}) "
                f"{target.get('context', '')}"
            )
        return "\n".join(lines)

    def _heuristic_select(
        self,
        query: str,
        neighbors: List[Dict[str, Any]],
        max_choices: int = 3
    ) -> List[int]:
        query_tokens = set(_tokenize(query))
        scored = []

        for idx, neighbor in enumerate(neighbors):
            target = neighbor["target"]
            text = f"{target.get('name', '')} {target.get('context', '')}"
            target_tokens = set(_tokenize(text))
            score = len(query_tokens & target_tokens)

            # Light type-aware boosts
            if {"error", "issue", "problem"} & query_tokens and target.get("type") == "problem":
                score += 1
            if {"fix", "solve", "solution", "how"} & query_tokens and target.get("type") == "solution":
                score += 1

            scored.append((score, idx))

        scored.sort(reverse=True)
        selected = [idx for score, idx in scored if score > 0][:max_choices]

        if not selected:
            selected = [idx for _, idx in scored[: min(max_choices, len(scored))]]

        return selected

    def _llm_decide_traversal(
        self,
        query: str,
        current_nodes: List[Dict[str, Any]],
        neighbors: List[Dict[str, Any]],
        context_so_far: Dict[str, Any],
        depth: int
    ) -> Dict[str, Any]:
        if not neighbors:
            return {"action": "STOP", "selected_nodes": [], "selected_relationships": [], "reasoning": "No neighbors."}

        prompt = f"""
You are guiding knowledge-graph traversal to answer a user question.

QUERY:
{query}

CURRENT NODES:
{self._format_nodes(current_nodes)}

NEIGHBORS (choose indices to explore):
{self._format_neighbors(neighbors)}

Rules:
- Select up to 4 neighbor indices that are most relevant.
- If you already have enough context to answer, return STOP.

Return JSON:
{{
  "action": "CONTINUE|STOP",
  "selected_indices": [0, 2],
  "reasoning": "short explanation"
}}
"""

        response = self.llm.generate_response(messages=[{"role": "user", "content": prompt}])
        data = _safe_json_loads(response, {})

        action = str(data.get("action", "CONTINUE")).upper()
        selected_indices = data.get("selected_indices")

        if not isinstance(selected_indices, list) or not selected_indices:
            selected_indices = self._heuristic_select(query, neighbors)
            action = "CONTINUE"

        selected_nodes = []
        selected_relationships = []

        for idx in selected_indices:
            if not isinstance(idx, int) or idx < 0 or idx >= len(neighbors):
                continue
            neighbor = neighbors[idx]
            target = neighbor["target"]
            selected_nodes.append(target)
            selected_relationships.append(
                {
                    "source_id": neighbor.get("source_id"),
                    "source_name": neighbor.get("source_name"),
                    "relationship": neighbor.get("relationship"),
                    "target_id": target.get("id"),
                    "target_name": target.get("name"),
                }
            )

        if action == "STOP":
            selected_nodes = []
            selected_relationships = []

        return {
            "action": action,
            "selected_nodes": selected_nodes,
            "selected_relationships": selected_relationships,
            "reasoning": data.get("reasoning", "Heuristic selection." if selected_nodes else "Stopped.")
        }

    def _estimate_size(self, context: Dict[str, Any]) -> int:
        try:
            return len(json.dumps(context, default=lambda o: list(o) if isinstance(o, set) else str(o)))
        except Exception:
            return 0

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "nodes": [],
            "relationships": [],
            "reasoning_trace": [],
            "depth_reached": 0,
            "total_nodes": 0
        }


# ================================================================
# WHAT INFORMATION TO STORE IN GRAPH NODES
# ================================================================

"""
GRAPH NODE SCHEMA (Complete)
============================

Common Fields (All Nodes):
-------------------------
{
    "id": "service_abc123",           # Unique ID
    "name": "AWS S3",                 # Human-readable name
    "type": "service|problem|solution", # Node type
    "level": 1-3,                     # Hierarchy level
    
    # Links
    "chat_ids": ["chat_1", "chat_2"], # All chats mentioning this
    "vector_refs": ["vec_1", "vec_2"], # Vector DB references
    
    # Context
    "context": "...",                 # Brief description
    "embedding": [...],               # For similarity search
    
    # Metadata
    "user_id": "user_123",
    "created_at": "2024-02-05T...",
    "updated_at": "2024-02-05T...",
    "mention_count": 15,              # Usage frequency
    "importance": 0.85,               # Calculated importance (0-1)
}

Type-Specific Fields:
--------------------

Concept/Service/Tool Node:
{
    ...(common fields),
    "common_issues": ["403 errors", "CORS"],
    "related_tools": ["AWS CLI", "boto3"],
    "documentation_links": ["https://..."]
}

Problem Node:
{
    ...(common fields),
    "symptoms": ["403 response", "access denied"],
    "contexts": ["Lambda access", "cross-account"],
    "frequency": 0.8,  # How common this problem is
}

Solution Node:
{
    ...(common fields),
    "steps": ["step 1", "step 2"],
    "success_rate": 0.95,  # Based on user feedback
    "prerequisites": ["IAM role", "bucket exists"],
    "alternatives": ["solution_xyz"]  # Other solution IDs
}
"""
