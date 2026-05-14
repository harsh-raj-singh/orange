from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.graph_schema import (
    GraphNode,
    LEVEL_PRIMARY,
    LEVEL_SECONDARY,
    NODE_TYPES,
    RELATIONSHIP_TYPES,
    SESSION_INTENTS,
)

from .signatures import dspy_available, get_dspy_module


NODE_DECOMPOSITION_INSTRUCTION = (
    "Given a conversation, extract a structured set of nodes. First identify the session intent. "
    "Then extract: the central problem(s) if any, what was attempted, what worked, what failed, "
    "key concepts referenced, any artifacts produced, any unresolved questions. For each node assign "
    "a type from NODE_TYPES, a level from 1-4, an outcome if applicable, and a 1-2 sentence context. "
    "Return only nodes that contain meaningful reusable information — skip pleasantries, filler, and "
    "obvious facts. Then declare relationships between nodes using RELATIONSHIP_TYPES only."
)

DECOMPOSE_PROMPT = """
You are extracting structured memory nodes from a conversation.

Valid node_types: session, problem, attempt, solution, concept, context, decision, open_question, artifact
Valid outcomes: worked, failed, partial, unknown

Extract nodes from this conversation. Return valid JSON only:
{
  "session_intent": "<one of: debugging, code_review, brainstorming, planning, learning, decision_making, general>",
  "nodes": [
    {
      "name": "<descriptive name, max 80 chars>",
      "node_type": "<from valid list>",
      "level": <2, 3, or 4>,
      "context": "<1-2 sentences of detail>",
      "outcome": "<from valid outcomes>"
    }
  ],
  "relationships": [
    {
      "source": "<node name>",
      "relation": "<one of: HAS_PROBLEM, ATTEMPTED, SOLVED_BY, FAILED_BECAUSE, RELATED_TO, DEPENDS_ON, LED_TO, PART_OF, REFERENCES, CONTRADICTS, PARTIAL_FIX>",
      "target": "<node name>"
    }
  ]
}

Rules:
- Always include at least one problem node if any issue was discussed
- Always include solution or attempt nodes if anything was tried
- Include concept nodes for every technology, tool, or pattern mentioned
- Include context nodes for environment details (language, framework, version)
- Do not include a session node — that is added automatically
- Return only JSON, no explanation
"""


def _normalize_intent(raw: Optional[str], fallback: str = "general") -> str:
    if isinstance(raw, str) and raw in SESSION_INTENTS:
        return raw
    return fallback


def _short_name(text: str, default_value: str) -> str:
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return default_value
    return cleaned[:100]


def _fallback_display_name(name: str, default_value: str) -> str:
    words = [w for w in (name or "").strip().split() if w]
    if not words:
        return default_value
    return " ".join(words[:4]).title()


class ConceptGraphExtractor:
    def __init__(self, llm: Optional[Any] = None):
        self.llm = llm
        self._predict = None
        self._signature = None
        if dspy_available():
            dspy = get_dspy_module()

            class NodeDecompositionSignature(dspy.Signature):
                """Given a conversation, extract a structured set of nodes. First identify the session intent. Then extract: the central problem(s) if any, what was attempted, what worked, what failed, key concepts referenced, any artifacts produced, any unresolved questions. For each node assign a type from NODE_TYPES, a level from 1-4, an outcome if applicable, and a 1-2 sentence context. Return only nodes that contain meaningful reusable information — skip pleasantries, filler, and obvious facts. Then declare relationships between nodes using RELATIONSHIP_TYPES only."""

                conversation_messages: str = dspy.InputField(desc="Conversation transcript")
                payload_json: str = dspy.InputField(desc="Extracted payload JSON")
                constraints_json: str = dspy.InputField(
                    desc="JSON with NODE_TYPES, RELATIONSHIP_TYPES, SESSION_INTENTS, level semantics"
                )

                session_intent: str = dspy.OutputField(desc="One value from SESSION_INTENTS")
                nodes_json: str = dspy.OutputField(desc="JSON array of nodes")
                relationships_json: str = dspy.OutputField(desc="JSON array of relationships")

            self._signature = NodeDecompositionSignature
            self._predict = dspy.Predict(NodeDecompositionSignature)

    def _build_graph_node(
        self,
        node: Dict[str, Any],
        *,
        chat_id: str,
        user_id: str,
        session_intent: str,
        extraction_version: str,
        source_type: str = "chat",
    ) -> Optional[GraphNode]:
        if not isinstance(node, dict):
            return None

        node_type = node.get("node_type") or node.get("type")
        if node_type not in NODE_TYPES:
            return None

        now = datetime.now(timezone.utc)
        try:
            return GraphNode(
                id=str(node.get("id") or uuid4()),
                name=_short_name(str(node.get("name", "")), f"{node_type.title()} Node"),
                display_name=_fallback_display_name(
                    str(node.get("display_name") or node.get("name") or ""),
                    f"{node_type.title()} Node",
                ),
                node_type=node_type,
                level=int(node.get("level", LEVEL_PRIMARY if node_type in {"problem", "decision", "open_question"} else LEVEL_SECONDARY)),
                context=str(node.get("context", "")).strip()[:300],
                session_intent=session_intent,
                source_type=source_type,
                chat_ids=[chat_id] if chat_id else [],
                vector_refs=[],
                user_ids=[user_id] if user_id else [],
                embedding=None,
                mention_count=int(node.get("mention_count", 1)),
                importance=float(node.get("importance", 0.5)),
                outcome=node.get("outcome", "unknown"),
                created_at=node.get("created_at") or now,
                updated_at=node.get("updated_at") or now,
                extraction_version=extraction_version,
            )
        except Exception:
            return None

    def _normalize_relationships(
        self,
        relationships: Any,
        *,
        valid_node_ids: set[str],
    ) -> List[Dict[str, str]]:
        normalized: List[Dict[str, str]] = []
        if not isinstance(relationships, list):
            return normalized

        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            source_id = str(rel.get("source_id") or rel.get("source") or "").strip()
            target_id = str(rel.get("target_id") or rel.get("target") or "").strip()
            relation = str(rel.get("relation") or "").strip()
            if relation not in RELATIONSHIP_TYPES:
                continue
            if source_id not in valid_node_ids or target_id not in valid_node_ids:
                continue
            normalized.append(
                {
                    "source_id": source_id,
                    "relation": relation,
                    "target_id": target_id,
                }
            )
        return normalized

    def _fallback_decompose(
        self,
        conversation_messages: str,
        payload: Dict[str, Any],
        *,
        chat_id: str,
        user_id: str,
        extraction_version: str,
    ) -> Dict[str, Any]:
        session_intent = _normalize_intent(payload.get("type"), "general")
        relationships: List[Dict[str, str]] = []
        nodes: List[GraphNode] = []
        llm_nodes: Any = []
        llm_relationships: Any = []

        if self.llm:
            prompt = (
                f"{DECOMPOSE_PROMPT}\n\nConversation:\n{conversation_messages}\n\n"
                f"Payload:\n{json.dumps(payload, ensure_ascii=True)}"
            )
            try:
                response = self.llm.generate_response(messages=[{"role": "user", "content": prompt}])
                response_text = str(response or "").strip()
                if response_text.startswith("```json"):
                    response_text = response_text.split("```json", 1)[1].split("```", 1)[0].strip()
                elif response_text.startswith("```"):
                    response_text = response_text.split("```", 1)[1].split("```", 1)[0].strip()
                parsed = json.loads(response_text)
                if isinstance(parsed, dict):
                    session_intent = _normalize_intent(parsed.get("session_intent"), session_intent)
                    llm_nodes = parsed.get("nodes", [])
                    llm_relationships = parsed.get("relationships", [])
            except Exception:
                llm_nodes = []
                llm_relationships = []

        for raw in llm_nodes if isinstance(llm_nodes, list) else []:
            if not isinstance(raw, dict):
                continue
            node_type = str(raw.get("node_type") or raw.get("type") or "").strip()
            if node_type == "session":
                continue
            if node_type not in NODE_TYPES:
                continue
            built = self._build_graph_node(
                {
                    "id": str(raw.get("id") or uuid4()),
                    "name": _short_name(str(raw.get("name", "")), f"{node_type.title()} Node"),
                    "node_type": node_type,
                    "level": raw.get("level", LEVEL_PRIMARY if node_type in {"problem", "decision", "open_question"} else LEVEL_SECONDARY),
                    "context": str(raw.get("context", "")).strip()[:300],
                    "outcome": raw.get("outcome", "unknown"),
                    "importance": raw.get("importance", 0.6),
                },
                chat_id=chat_id,
                user_id=user_id,
                session_intent=session_intent,
                extraction_version=extraction_version,
            )
            if built:
                nodes.append(built)

        if nodes:
            for rel in llm_relationships if isinstance(llm_relationships, list) else []:
                if not isinstance(rel, dict):
                    continue
                relation = str(rel.get("relation") or "").strip()
                source_name = str(rel.get("source") or rel.get("source_id") or "").strip()
                target_name = str(rel.get("target") or rel.get("target_id") or "").strip()
                if source_name and target_name and relation in RELATIONSHIP_TYPES:
                    relationships.append(
                        {
                            "source": source_name,
                            "relation": relation,
                            "target": target_name,
                        }
                    )

        if not nodes:
            lines = [line.strip() for line in (conversation_messages or "").splitlines() if line.strip()]
            has_question_or_error = any(
                ("?" in line) or re.search(r"\b(error|exception|failed|issue)\b", line.lower())
                for line in lines
            )
            solution_payload = payload.get("solution")
            has_resolution = bool(solution_payload or payload.get("resolution") or payload.get("answer"))

            problem_node: Optional[GraphNode] = None
            if has_question_or_error:
                user_lines = [line for line in lines if "] user:" in line.lower()]
                problem_text = user_lines[0].split(":", 1)[-1].strip() if user_lines else (lines[0] if lines else "Open problem")
                problem_node = self._build_graph_node(
                    {
                        "name": problem_text,
                        "node_type": "problem",
                        "level": LEVEL_PRIMARY,
                        "context": "Issue raised during conversation that may need reuse later.",
                        "importance": 0.7,
                        "outcome": "unknown",
                    },
                    chat_id=chat_id,
                    user_id=user_id,
                    session_intent=session_intent,
                    extraction_version=extraction_version,
                )
                if problem_node:
                    nodes.append(problem_node)

            if has_resolution:
                if isinstance(solution_payload, dict):
                    solution_line = (
                        str(solution_payload.get("summary") or "")
                        or str(solution_payload.get("resolution") or "")
                        or str(solution_payload.get("solution") or "")
                    ).strip()
                else:
                    solution_line = str(solution_payload or payload.get("resolution") or payload.get("answer") or "").strip()
                if not solution_line:
                    solution_line = "Conversation resolution captured."
                solution_node = self._build_graph_node(
                    {
                        "name": solution_line,
                        "node_type": "solution",
                        "level": LEVEL_SECONDARY,
                        "context": "Confirmed outcome from this session.",
                        "importance": 0.75,
                        "outcome": "unknown",
                    },
                    chat_id=chat_id,
                    user_id=user_id,
                    session_intent=session_intent,
                    extraction_version=extraction_version,
                )
                if solution_node:
                    nodes.append(solution_node)
                    if problem_node:
                        relationships.append(
                            {
                                "source": problem_node.name,
                                "relation": "SOLVED_BY",
                                "target": solution_node.name,
                            }
                        )

            if not nodes:
                seed = _short_name(payload.get("topic") or payload.get("summary") or "Conversation context", "Conversation context")
                concept_node = self._build_graph_node(
                    {
                        "name": seed,
                        "node_type": "concept",
                        "level": LEVEL_SECONDARY,
                        "context": "General reusable context captured from this session.",
                        "importance": 0.5,
                        "outcome": "unknown",
                    },
                    chat_id=chat_id,
                    user_id=user_id,
                    session_intent=session_intent,
                    extraction_version=extraction_version,
                )
                if concept_node:
                    nodes.append(concept_node)

        return {
            "session_intent": session_intent,
            "nodes": [node.model_dump(mode="json") for node in nodes],
            "relationships": relationships,
        }

    def decompose_into_nodes(
        self,
        conversation_messages: str,
        payload: Dict[str, Any],
        *,
        chat_id: str = "",
        user_id: str = "",
        extraction_version: str = "dspy_v1",
    ) -> Dict[str, Any]:
        if self._predict:
            try:
                constraints = {
                    "instruction": NODE_DECOMPOSITION_INSTRUCTION,
                    "node_types": NODE_TYPES,
                    "relationship_types": RELATIONSHIP_TYPES,
                    "session_intents": SESSION_INTENTS,
                    "levels": {
                        "1": "session",
                        "2": "primary",
                        "3": "secondary",
                        "4": "detail",
                    },
                }
                result = self._predict(
                    conversation_messages=conversation_messages,
                    payload_json=json.dumps(payload),
                    constraints_json=json.dumps(constraints),
                )
                session_intent = _normalize_intent(getattr(result, "session_intent", None), _normalize_intent(payload.get("type")))
                raw_nodes = json.loads(getattr(result, "nodes_json", "[]"))
                raw_relationships = json.loads(getattr(result, "relationships_json", "[]"))

                nodes: List[GraphNode] = []
                for raw in raw_nodes if isinstance(raw_nodes, list) else []:
                    node = self._build_graph_node(
                        raw,
                        chat_id=chat_id,
                        user_id=user_id,
                        session_intent=session_intent,
                        extraction_version=extraction_version,
                    )
                    if node:
                        nodes.append(node)

                valid_ids = {node.id for node in nodes}
                relationships = self._normalize_relationships(raw_relationships, valid_node_ids=valid_ids)

                if nodes:
                    return {
                        "session_intent": session_intent,
                        "nodes": [node.model_dump(mode="json") for node in nodes],
                        "relationships": relationships,
                    }
            except Exception:
                pass

        return self._fallback_decompose(
            conversation_messages,
            payload,
            chat_id=chat_id,
            user_id=user_id,
            extraction_version=extraction_version,
        )

    def forward(self, conversation_messages: str, payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Backward-compatible wrapper used by extraction pipeline.
        Returns both:
        - nodes/relationships (new)
        - concepts/relationships (legacy shape for formatter)
        """
        decomposed = self.decompose_into_nodes(
            conversation_messages,
            payload,
            chat_id=str(payload.get("chat_id", "")),
            user_id=str(payload.get("user_id", "")),
            extraction_version=str(payload.get("extraction_version", "dspy_v1")),
        )
        nodes = decomposed.get("nodes", [])
        legacy_concepts = [
            {
                "name": node.get("name", ""),
                "type": node.get("node_type", "concept"),
                "level": node.get("level", LEVEL_PRIMARY),
                "context": node.get("context", ""),
            }
            for node in nodes
            if isinstance(node, dict)
        ]
        return {
            "session_intent": decomposed.get("session_intent", "general"),
            "nodes": nodes,
            "concepts": legacy_concepts,
            "relationships": decomposed.get("relationships", []),
        }
