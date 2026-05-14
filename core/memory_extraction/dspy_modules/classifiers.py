from __future__ import annotations

import json
import re
from typing import Any, Dict

from .signatures import ConversationTypeClassifier, dspy_available, get_dspy_module


def _heuristic_classify(conversation: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    low = conversation.lower()

    if any(k in low for k in ["error", "exception", "traceback", "failed", "doesn't work", "didn't work"]):
        return {
            "conversation_type": "debugging",
            "should_extract": True,
            "extraction_depth": "deep",
            "reasoning": "Error-driven multi-turn problem solving detected",
        }

    if any(k in low for k in ["pros", "cons", "tradeoff", "architecture", "should we", "option"]):
        return {
            "conversation_type": "brainstorming",
            "should_extract": True,
            "extraction_depth": "medium",
            "reasoning": "Decision/tradeoff discussion detected",
        }

    if any(k in low for k in ["review", "refactor", "performance", "codebase", "pull request", "bug"]):
        return {
            "conversation_type": "code_review",
            "should_extract": True,
            "extraction_depth": "medium",
            "reasoning": "Code quality analysis detected",
        }

    if any(k in low for k in ["capital of", "weather", "hello", "hi ", "thank you"]):
        return {
            "conversation_type": "casual",
            "should_extract": False,
            "extraction_depth": "shallow",
            "reasoning": "Trivial or casual conversation",
        }

    if metadata.get("memory_request_reason"):
        return {
            "conversation_type": "learning",
            "should_extract": True,
            "extraction_depth": "deep",
            "reasoning": "Memory requested explicitly",
        }

    return {
        "conversation_type": "learning",
        "should_extract": False,
        "extraction_depth": "shallow",
        "reasoning": "No high-value long-term signal detected",
    }


class ConversationClassifier:
    def __init__(self):
        self._predict = None
        if dspy_available():
            dspy = get_dspy_module()
            self._predict = dspy.Predict(ConversationTypeClassifier)

    def forward(self, conversation_messages: str, context_metadata: Dict[str, Any]) -> Dict[str, Any]:
        if not self._predict:
            return _heuristic_classify(conversation_messages, context_metadata)

        try:
            result = self._predict(
                conversation_messages=conversation_messages,
                context_metadata=json.dumps(context_metadata),
            )
            return {
                "conversation_type": str(result.conversation_type),
                "should_extract": bool(result.should_extract),
                "extraction_depth": str(result.extraction_depth),
                "reasoning": str(result.reasoning),
            }
        except Exception:
            return _heuristic_classify(conversation_messages, context_metadata)


def extract_first_error(conversation_messages: str) -> str:
    for line in conversation_messages.splitlines():
        if re.search(r"error|exception|traceback", line, re.IGNORECASE):
            return line.split(":", 1)[-1].strip()
    return ""
