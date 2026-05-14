from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from pydantic import ValidationError

from core.memory_extraction.schemas import Concept, ConversationMetadata, ExtractedMemory, Relationship, SearchableSummary

from .signatures import ImportanceConfidenceSignature, SearchableSummarySignature, dspy_available, get_dspy_module


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class MemoryFormatter:
    def __init__(self, extraction_version: str = "dspy_v1"):
        self.extraction_version = extraction_version
        self._summary_predict = None
        self._importance_predict = None
        if dspy_available():
            dspy = get_dspy_module()
            self._summary_predict = dspy.Predict(SearchableSummarySignature)
            self._importance_predict = dspy.Predict(ImportanceConfidenceSignature)

    def _fallback_searchable_summary(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if payload.get("type") == "debugging":
            problem = payload.get("problem", {})
            solution = payload.get("solution", {})
            return {
                "query_intent": problem.get("description", ""),
                "solution_summary": solution.get("fix_applied", ""),
                "keywords": [
                    k
                    for k in [
                        problem.get("context", {}).get("platform"),
                        problem.get("context", {}).get("service"),
                        "debugging",
                    ]
                    if k
                ],
            }

        return {
            "query_intent": payload.get("topic") or payload.get("codebase_summary") or "",
            "solution_summary": payload.get("decision", {}).get("chosen") if isinstance(payload.get("decision"), dict) else "",
            "keywords": [payload.get("type", "")],
        }

    def _predict_scores(self, conversation: str, payload: Dict[str, Any]) -> Dict[str, float]:
        if self._importance_predict:
            try:
                result = self._importance_predict(
                    conversation_messages=conversation,
                    payload_json=json.dumps(payload),
                )
                return {
                    "importance_score": _clip01(result.importance_score),
                    "extraction_confidence": _clip01(result.extraction_confidence),
                }
            except Exception:
                pass

        # Heuristic scoring
        score = 0.4
        confidence = 0.5
        ptype = payload.get("type")
        if ptype == "debugging":
            score += 0.35
            if payload.get("problem", {}).get("exact_error"):
                confidence += 0.2
        elif ptype in {"brainstorming", "code_review"}:
            score += 0.25
            confidence += 0.1

        if payload.get("failed_solutions"):
            score += 0.1
        return {
            "importance_score": _clip01(score),
            "extraction_confidence": _clip01(confidence),
        }

    def _predict_searchable(self, conversation: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._summary_predict:
            try:
                result = self._summary_predict(
                    conversation_messages=conversation,
                    payload_json=json.dumps(payload),
                )
                keywords = json.loads(result.keywords_json)
                if not isinstance(keywords, list):
                    keywords = []
                return {
                    "query_intent": str(result.query_intent),
                    "solution_summary": str(result.solution_summary),
                    "keywords": [str(k) for k in keywords if isinstance(k, (str, int, float))],
                }
            except Exception:
                pass
        return self._fallback_searchable_summary(payload)

    def format_and_validate(
        self,
        chat: Dict[str, Any],
        classification: Dict[str, Any],
        payload: Dict[str, Any],
        concept_graph: Dict[str, List[Dict[str, Any]]],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        searchable = self._predict_searchable(metadata.get("conversation", ""), payload)
        scores = self._predict_scores(metadata.get("conversation", ""), payload)

        concepts = [Concept(**c) for c in concept_graph.get("concepts", []) if isinstance(c, dict)]
        relationships = [Relationship(**r) for r in concept_graph.get("relationships", []) if isinstance(r, dict)]

        extracted = ExtractedMemory(
            chat_id=chat["chat_id"],
            user_id=chat["user_id"],
            extracted_at=datetime.now(timezone.utc).isoformat(),
            conversation_metadata=ConversationMetadata(
                type=classification.get("conversation_type", "learning"),
                turns=metadata.get("turns", len(chat.get("messages", [])) // 2),
                duration_minutes=metadata.get("duration_minutes", 0),
                marked_complete_by_user=True,
                success_outcome=bool(payload.get("solution", {}).get("verification") if isinstance(payload.get("solution"), dict) else False),
                extraction_depth=classification.get("extraction_depth", "medium"),
            ),
            memory_payload=payload,
            extracted_concepts=concepts,
            relationships=relationships,
            searchable_summary=SearchableSummary(**searchable),
            importance_score=scores["importance_score"],
            extraction_confidence=scores["extraction_confidence"],
            extraction_version=self.extraction_version,
            processing_state="processed",
        )
        return extracted.model_dump()

    def validate_with_repair(self, memory_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return ExtractedMemory(**memory_data).model_dump()
        except ValidationError as e:
            repaired = dict(memory_data)
            repaired["processing_state"] = repaired.get("processing_state") or "processed"
            repaired["importance_score"] = _clip01(repaired.get("importance_score", 0.3))
            repaired["extraction_confidence"] = _clip01(repaired.get("extraction_confidence", 0.2))
            repaired["skip_reason"] = repaired.get("skip_reason") or f"repair_applied: {str(e)[:180]}"
            return ExtractedMemory(**repaired).model_dump()
