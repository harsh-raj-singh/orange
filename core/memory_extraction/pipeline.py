from __future__ import annotations

import concurrent.futures
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.memory_extraction.config import ExtractionConfig
from core.memory_extraction.dspy_modules import (
    ConceptGraphExtractor,
    ConversationClassifier,
    DetailExtractor,
    MemoryFormatter,
    NegativePathCapture,
)
from core.memory_extraction.preprocessing import preprocess_chat

logger = logging.getLogger(__name__)


class DSPyMemoryExtractor:
    def __init__(
        self,
        llm: Any,
        config: Optional[ExtractionConfig] = None,
        summarization_agent: Optional[Any] = None,
        importance_agent: Optional[Any] = None,
        concept_agent: Optional[Any] = None,
    ):
        self.llm = llm
        self.config = config or ExtractionConfig()

        # Legacy agents retained for controlled rollout fallback.
        self.summarization_agent = summarization_agent
        self.importance_agent = importance_agent
        self.concept_agent = concept_agent

        self._configure_dspy_backend()

        self.classifier = ConversationClassifier()
        self.extractor = DetailExtractor()
        self.negative_path = NegativePathCapture()
        self.concept_graph = ConceptGraphExtractor(llm=self.llm)
        self.formatter = MemoryFormatter(extraction_version=self.config.EXTRACTION_VERSION)

    def _configure_dspy_backend(self) -> None:
        try:
            import dspy  # type: ignore
        except Exception:
            logger.info("dspy_not_available_using_heuristics")
            return

        cfg = getattr(self.llm, "config", None)
        model = getattr(cfg, "model", None)
        api_key = getattr(cfg, "api_key", None)
        api_base = getattr(cfg, "openai_base_url", None)
        if not model or not api_key:
            logger.info("dspy_config_skipped_missing_model_or_api_key")
            return

        try:
            lm = dspy.LM(
                model=f"openai/{model}",
                api_key=api_key,
                api_base=api_base,
                temperature=0.2,
                max_tokens=2000,
            )
            dspy.configure(lm=lm)
            logger.info("dspy_configured", extra={"model": model})
        except Exception as exc:  # noqa: BLE001
            logger.warning("dspy_config_failed", extra={"error": str(exc), "model": model})

    def extract_chat_memory(self, chat: Dict[str, Any]) -> Dict[str, Any]:
        """Extract memory with DSPy + optional legacy fallback."""
        started = time.monotonic()

        if not self.config.USE_DSPY_EXTRACTION:
            logger.info("DSPy extraction disabled via feature flag", extra={"chat_id": chat.get("chat_id")})
            result = self._legacy_extraction(chat)
            self._log_outcome(chat, result, started, fallback_used=False)
            return result

        try:
            memory = self._dspy_extract(chat)

            if self.config.DUAL_WRITE_MODE:
                legacy_memory = self._legacy_extraction(chat)
                self._log_comparison(memory, legacy_memory, chat_id=chat.get("chat_id"))

            self._log_outcome(chat, memory, started, fallback_used=False)
            return memory

        except Exception as exc:  # noqa: BLE001
            logger.error("DSPy extraction failed", extra={"chat_id": chat.get("chat_id"), "error": str(exc)}, exc_info=True)

            if self.config.FALLBACK_TO_LEGACY:
                logger.info("Falling back to legacy extraction", extra={"chat_id": chat.get("chat_id")})
                fallback = self._legacy_extraction(chat)
                self._log_outcome(chat, fallback, started, fallback_used=True, error_type=type(exc).__name__)
                return fallback

            minimal = self._create_minimal_fallback(chat, error=str(exc))
            self._log_outcome(chat, minimal, started, fallback_used=False, error_type=type(exc).__name__)
            return minimal

    def _dspy_extract(self, chat: Dict[str, Any]) -> Dict[str, Any]:
        last_error: Optional[Exception] = None

        for attempt in range(self.config.MAX_EXTRACTION_RETRIES):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self._dspy_extract_once, chat)
                    return future.result(timeout=self.config.EXTRACTION_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError as exc:
                last_error = exc
                logger.warning(
                    "DSPy extraction timeout",
                    extra={"chat_id": chat.get("chat_id"), "attempt": attempt + 1},
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "DSPy extraction error",
                    extra={"chat_id": chat.get("chat_id"), "attempt": attempt + 1, "error": str(exc)},
                )

            if attempt < self.config.MAX_EXTRACTION_RETRIES - 1:
                time.sleep(2**attempt)

        raise RuntimeError("DSPy extraction failed after all retries") from last_error

    def _dspy_extract_once(self, chat: Dict[str, Any]) -> Dict[str, Any]:
        preprocessed = preprocess_chat(chat)
        conversation = preprocessed["conversation"]
        metadata = preprocessed["metadata"]

        classification = self.classifier.forward(conversation, metadata)

        # Explicit request overrides skip for selective memory extraction.
        if metadata.get("memory_request_reason") and not classification.get("should_extract"):
            classification["should_extract"] = True
            classification["extraction_depth"] = "deep"
            classification["reasoning"] = (
                f"override: explicit request ({metadata.get('memory_request_reason')})"
            )

        if not classification.get("should_extract", False):
            return self._create_skip_result(classification.get("reasoning", "classifier_skip"), classification)

        payload = self.extract_type_payload(classification.get("conversation_type", "learning"), conversation, metadata)

        failed_paths = self.capture_negative_paths(conversation, payload)
        if failed_paths:
            payload["failed_solutions"] = failed_paths

        concepts = self.extract_concept_graph(conversation, payload)

        memory = self.format_and_validate(
            chat,
            {
                "classification": classification,
                "payload": payload,
                "concepts": concepts,
                "metadata": metadata,
                "conversation": conversation,
            },
        )

        if memory.get("extraction_confidence", 0.0) < self.config.MIN_CONFIDENCE_FOR_STORAGE:
            return self._create_skip_result(
                f"low_confidence:{memory.get('extraction_confidence', 0.0):.2f}",
                classification,
            )

        return memory

    def extract_type_payload(self, conversation_type: str, conversation: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        return self.extractor.forward(conversation_type, conversation, metadata)

    def capture_negative_paths(self, conversation: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self.negative_path.forward(conversation, payload)

    def extract_concept_graph(self, conversation: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.concept_graph.forward(conversation, payload)

    def format_and_validate(self, chat: Dict[str, Any], components: Dict[str, Any]) -> Dict[str, Any]:
        memory = self.formatter.format_and_validate(
            chat,
            components["classification"],
            components["payload"],
            components["concepts"],
            {
                **components.get("metadata", {}),
                "conversation": components.get("conversation", ""),
            },
        )
        return self.formatter.validate_with_repair(memory)

    def _legacy_extraction(self, chat: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy summarization-based extraction (fallback path)."""
        if not self.summarization_agent or not self.importance_agent or not self.concept_agent:
            return self._create_minimal_fallback(chat, error="legacy_agents_unavailable")

        summaries = self.summarization_agent.process(chat)

        # If there's an explicit memory request (e.g. Slack /orange),
        # bypass the importance filter — user already signaled intent.
        explicit_request = chat.get("memory_request_reason")
        if explicit_request:
            logger.info(
                "Bypassing importance filter: explicit memory request (%s)",
                explicit_request,
                extra={"chat_id": chat.get("chat_id")},
            )
            importance = {
                "should_store": True,
                "importance_score": 0.8,
                "reason": f"explicit_request: {explicit_request}",
                "storage_targets": ["vector", "graph"],
                "tags": [],
            }
        else:
            importance = self.importance_agent.should_store(chat, summaries)

        if not importance.get("should_store", False):
            return self._create_skip_result(importance.get("reason", "legacy_skip"), {
                "conversation_type": summaries.get("conversation_type", "casual"),
                "extraction_depth": "shallow",
            })

        concepts_data = self.concept_agent.extract(chat, summaries)

        return {
            "chat_id": chat["chat_id"],
            "user_id": chat["user_id"],
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "conversation_metadata": {
                "type": summaries.get("conversation_type", "legacy"),
                "turns": len(chat.get("messages", [])) // 2,
                "duration_minutes": 0,
                "marked_complete_by_user": True,
                "success_outcome": summaries.get("was_successful", True),
                "extraction_depth": "medium",
            },
            "memory_payload": {
                "type": "legacy",
                "query_summary": summaries.get("query_summary", ""),
                "response_summary": summaries.get("response_summary", ""),
                "key_points": summaries.get("key_points", []),
            },
            "extracted_concepts": concepts_data.get("concepts", []) + concepts_data.get("problems", []) + concepts_data.get("solutions", []),
            "relationships": concepts_data.get("relationships", []),
            "searchable_summary": {
                "query_intent": summaries.get("query_summary", ""),
                "solution_summary": summaries.get("response_summary", ""),
                "keywords": importance.get("tags", []),
            },
            "importance_score": float(importance.get("importance_score", 0.5)),
            "extraction_confidence": 0.5,
            "extraction_version": "legacy_v1",
            "processing_state": "processed",
            "skip_reason": None,
        }

    def _create_skip_result(self, reason: str, classification: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        classification = classification or {}
        return {
            "processing_state": "skipped",
            "conversation_type": classification.get("conversation_type", "casual"),
            "reason": reason,
            "importance_score": 0.0,
            "extraction_confidence": 1.0,
        }

    def _create_minimal_fallback(self, chat: Dict[str, Any], error: str) -> Dict[str, Any]:
        user_messages = [m.get("content", "") for m in chat.get("messages", []) if m.get("role") == "user"]
        assistant_messages = [m.get("content", "") for m in chat.get("messages", []) if m.get("role") == "assistant"]

        return {
            "chat_id": chat.get("chat_id", ""),
            "user_id": chat.get("user_id", ""),
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "conversation_metadata": {
                "type": "fallback",
                "turns": len(chat.get("messages", [])) // 2,
                "duration_minutes": 0,
                "marked_complete_by_user": True,
                "success_outcome": False,
                "extraction_depth": "shallow",
            },
            "memory_payload": {
                "type": "fallback",
                "error": error,
                "first_user_message": user_messages[0][:200] if user_messages else "",
                "last_assistant_message": assistant_messages[-1][:200] if assistant_messages else "",
                "turn_count": len(chat.get("messages", [])) // 2,
            },
            "extracted_concepts": [],
            "relationships": [],
            "searchable_summary": {
                "query_intent": user_messages[0][:120] if user_messages else "",
                "solution_summary": assistant_messages[-1][:120] if assistant_messages else "",
                "keywords": ["fallback"],
            },
            "importance_score": 0.3,
            "extraction_confidence": 0.0,
            "extraction_version": self.config.EXTRACTION_VERSION,
            "processing_state": "processed",
            "skip_reason": None,
        }

    def _log_comparison(self, dspy_memory: Dict[str, Any], legacy_memory: Dict[str, Any], chat_id: Optional[str]) -> None:
        payload = {
            "chat_id": chat_id,
            "dspy_type": (dspy_memory.get("conversation_metadata") or {}).get("type"),
            "legacy_type": (legacy_memory.get("conversation_metadata") or {}).get("type"),
            "dspy_importance": dspy_memory.get("importance_score"),
            "legacy_importance": legacy_memory.get("importance_score"),
            "dspy_keywords": (dspy_memory.get("searchable_summary") or {}).get("keywords"),
            "legacy_keywords": (legacy_memory.get("searchable_summary") or {}).get("keywords"),
        }
        logger.info("dual_write_comparison", extra={"comparison": payload})

    def _log_outcome(
        self,
        chat: Dict[str, Any],
        memory: Dict[str, Any],
        started: float,
        fallback_used: bool,
        error_type: Optional[str] = None,
    ) -> None:
        duration_ms = int((time.monotonic() - started) * 1000)
        conversation_type = (
            (memory.get("conversation_metadata") or {}).get("type")
            or memory.get("conversation_type")
            or "unknown"
        )
        logger.info(
            "memory_extraction_result",
            extra={
                "chat_id": chat.get("chat_id"),
                "conversation_type": conversation_type,
                "success": memory.get("processing_state") != "failed",
                "processing_ms": duration_ms,
                "confidence": memory.get("extraction_confidence", 0.0),
                "importance": memory.get("importance_score", 0.0),
                "fallback_used": fallback_used,
                "error_type": error_type,
            },
        )
