from __future__ import annotations

import json
import re
from typing import Any

from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from core.graph_schema_v2 import Problem
from core.graph_upsert.embeddings import build_problem_embed_string
from core.graph_upsert.models import MergeDecision

ORANGE_NODE_VECTOR_COLLECTION = "orange_node_vectors"
_EMBED_FN = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

ARBITRATION_PROMPT = """You are deciding whether two problem descriptions refer to the same underlying technical problem.

Problem A (new): {new_label} - {new_context}
Problem B (existing): {existing_label} - {existing_context}

Answer with JSON only:
{{"same_problem": true/false, "reasoning": "one sentence"}}

Be conservative: only return true if they are clearly the same root cause, not just related topics."""


class _FallbackCollection:
    def query(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"ids": [[]], "distances": [[]], "metadatas": [[]]}


def get_or_create_orange_collection(chroma: Any) -> Any:
    """Resolve the dedicated H4 collection, creating it on first use when supported."""

    if chroma is None:
        return _FallbackCollection()
    if callable(getattr(chroma, "query", None)):
        return chroma
    if callable(getattr(chroma, "get_or_create_collection", None)):
        return chroma.get_or_create_collection(
            ORANGE_NODE_VECTOR_COLLECTION,
            embedding_function=_EMBED_FN,
            metadata={"hnsw:space": "cosine"},
        )
    return chroma


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return {}
        payload = json.loads(match.group(0))
    return payload if isinstance(payload, dict) else {}


def _call_arbitration_llm(prompt: str, llm: Any) -> dict[str, Any]:
    if llm is None:
        return {}

    if callable(getattr(llm, "generate_response", None)):
        raw = llm.generate_response(messages=[{"role": "user", "content": prompt}])
        if isinstance(raw, (str, bytes, bytearray)):
            return _parse_json_object(raw.decode() if isinstance(raw, (bytes, bytearray)) else raw)

    if callable(llm):
        raw = llm(prompt)
        if isinstance(raw, (str, bytes, bytearray)):
            return _parse_json_object(raw.decode() if isinstance(raw, (bytes, bytearray)) else raw)

    return {}


def _top_result(query_result: dict[str, Any]) -> tuple[str | None, float | None, dict[str, Any]]:
    ids = (query_result or {}).get("ids") or [[]]
    distances = (query_result or {}).get("distances") or [[]]
    metadatas = (query_result or {}).get("metadatas") or [[]]

    top_id = ids[0][0] if ids and ids[0] else None
    top_distance = distances[0][0] if distances and distances[0] else None
    top_metadata = metadatas[0][0] if metadatas and metadatas[0] else {}

    return top_id, top_distance, top_metadata if isinstance(top_metadata, dict) else {}


def _filtered_problem_candidates(query_result: dict[str, Any], user_id: str, limit: int = 3) -> dict[str, Any]:
    """Filter unscoped query results to Problem+user documents when where-filter fails."""

    ids = (query_result or {}).get("ids") or [[]]
    distances = (query_result or {}).get("distances") or [[]]
    metadatas = (query_result or {}).get("metadatas") or [[]]

    filtered_ids: list[str] = []
    filtered_distances: list[float] = []
    filtered_metadatas: list[dict[str, Any]] = []

    rows = zip(ids[0] if ids else [], distances[0] if distances else [], metadatas[0] if metadatas else [])
    for candidate_id, candidate_distance, metadata in rows:
        if len(filtered_ids) >= limit:
            break
        if not isinstance(metadata, dict):
            continue
        if metadata.get("node_type") != "Problem":
            continue
        if metadata.get("user_id") != user_id:
            continue
        filtered_ids.append(str(candidate_id))
        filtered_distances.append(float(candidate_distance))
        filtered_metadatas.append(metadata)

    return {"ids": [filtered_ids], "distances": [filtered_distances], "metadatas": [filtered_metadatas]}


def _query_problem_candidates(collection: Any, embed_string: str, user_id: str) -> dict[str, Any]:
    """Query with strict where filter; fall back to client-side filtering on schema drift."""

    try:
        return collection.query(
            query_texts=[embed_string],
            n_results=3,
            where={"node_type": "Problem", "user_id": user_id},
        )
    except Exception:  # noqa: BLE001
        # Some collections may contain older docs missing filter fields.
        # Fall back to an unfiltered query and enforce node_type/user_id in Python.
        try:
            unscoped = collection.query(query_texts=[embed_string], n_results=20)
            return _filtered_problem_candidates(unscoped, user_id=user_id, limit=3)
        except Exception:  # noqa: BLE001
            return {"ids": [[]], "distances": [[]], "metadatas": [[]]}


def run_dedup(problem: Problem, user_id: str, chroma: Any, llm: Any = None) -> MergeDecision:
    """Run Problem dedup against orange_node_vectors using similarity thresholds + arbitration."""

    collection = get_or_create_orange_collection(chroma)
    embed_string = build_problem_embed_string(problem)
    result = _query_problem_candidates(collection, embed_string=embed_string, user_id=user_id)

    existing_id, top_distance, top_metadata = _top_result(result)
    if not existing_id or top_distance is None:
        return MergeDecision(action="CREATE", existing_node_id=None, similarity_score=None, arbitration_used=False)

    similarity = 1.0 - float(top_distance)

    if similarity > 0.80:
        return MergeDecision(
            action="MERGE",
            existing_node_id=existing_id,
            similarity_score=similarity,
            arbitration_used=False,
        )

    if similarity < 0.50:
        return MergeDecision(
            action="CREATE",
            existing_node_id=None,
            similarity_score=similarity,
            arbitration_used=False,
        )

    existing_label = str(top_metadata.get("canonical_label", "")).strip()
    existing_context = str(top_metadata.get("context_brief", "")).strip()
    prompt = ARBITRATION_PROMPT.format(
        new_label=problem.canonical_label,
        new_context=problem.context_brief,
        existing_label=existing_label,
        existing_context=existing_context,
    )

    arbitration = _call_arbitration_llm(prompt, llm)
    same_problem = bool(arbitration.get("same_problem", False))

    if same_problem:
        return MergeDecision(
            action="MERGE",
            existing_node_id=existing_id,
            similarity_score=similarity,
            arbitration_used=True,
        )

    return MergeDecision(
        action="CREATE",
        existing_node_id=existing_id,
        similarity_score=similarity,
        arbitration_used=True,
    )
