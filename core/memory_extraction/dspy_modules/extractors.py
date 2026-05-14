from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from .classifiers import extract_first_error
from .signatures import GenericTypeExtractor, dspy_available, get_dspy_module


def _lines_for_role(conversation_messages: str, role: str) -> List[str]:
    prefix = f"] {role}:"
    return [line for line in conversation_messages.splitlines() if prefix in line]


def _extract_debugging_heuristic(conversation_messages: str) -> Dict[str, Any]:
    user_lines = _lines_for_role(conversation_messages, "user")
    asst_lines = _lines_for_role(conversation_messages, "assistant")

    problem = user_lines[0].split(":", 1)[-1].strip() if user_lines else ""
    exact_error = extract_first_error(conversation_messages)

    investigation = []
    attempt = 1
    for idx, line in enumerate(asst_lines[:5], start=1):
        text = line.split(":", 1)[-1].strip()
        investigation.append(
            {
                "attempt": attempt,
                "action": text[:160],
                "result": "Attempt suggested",
                "outcome": "failed" if "didn't work" in conversation_messages.lower() else "unknown",
            }
        )
        attempt += 1

    verification = ""
    if any(k in conversation_messages.lower() for k in ["it worked", "fixed", "resolved", "succeeded"]):
        verification = "User confirmed the fix worked"

    return {
        "type": "debugging",
        "problem": {
            "description": problem,
            "exact_error": exact_error,
            "context": {
                "platform": "AWS" if "aws" in conversation_messages.lower() else None,
                "service": "Lambda" if "lambda" in conversation_messages.lower() else None,
                "region": "us-east-1" if "us-east-1" in conversation_messages.lower() else None,
                "environment": "production" if "production" in conversation_messages.lower() else None,
            },
            "symptoms": ["error reported"] if exact_error else [],
        },
        "investigation_path": investigation,
        "solution": {
            "root_cause": "Permission or configuration issue" if "denied" in conversation_messages.lower() else "Unknown",
            "fix_applied": asst_lines[-1].split(":", 1)[-1].strip()[:200] if asst_lines else "",
            "exact_steps": [
                "Review latest suggested fix",
                "Apply configuration update",
                "Retry operation",
            ],
            "verification": verification,
        },
        "llm_mistakes": [],
        "key_learnings": [],
    }


def _extract_brainstorming_heuristic(conversation_messages: str) -> Dict[str, Any]:
    options = []
    for i, line in enumerate(conversation_messages.splitlines(), start=1):
        if re.search(r"option|could use|use ", line, re.IGNORECASE):
            options.append(
                {
                    "option": line.split(":", 1)[-1].strip()[:140],
                    "pros": [],
                    "cons": [],
                    "discussed_in_messages": [i],
                }
            )
    return {
        "type": "brainstorming",
        "topic": conversation_messages.splitlines()[0][:120] if conversation_messages else "",
        "options_explored": options[:8],
        "decision": {
            "chosen": options[-1]["option"] if options else "",
            "reasoning": "Last discussed option selected",
            "tradeoffs_accepted": [],
            "recommendation": "Reuse this decision logic for similar constraints",
        },
    }


def _extract_code_review_heuristic(conversation_messages: str) -> Dict[str, Any]:
    issues = []
    suggestions = []
    for line in conversation_messages.splitlines():
        text = line.split(":", 1)[-1].strip()
        low = text.lower()
        if any(k in low for k in ["issue", "bug", "problem", "slow", "unoptimized"]):
            issues.append(
                {
                    "issue": text[:160],
                    "severity": "high" if "critical" in low or "high" in low else "medium",
                    "location": "",
                    "explanation": text[:180],
                }
            )
        if any(k in low for k in ["suggest", "use ", "should", "recommend"]):
            suggestions.append(
                {
                    "suggestion": text[:160],
                    "rationale": "Suggested during review",
                    "applied": "worked" in low or "applied" in low,
                    "outcome": "",
                }
            )

    return {
        "type": "code_review",
        "codebase_summary": "Code review conversation",
        "issues_found": issues[:10],
        "suggestions": suggestions[:10],
    }


def _extract_learning_heuristic(conversation_messages: str) -> Dict[str, Any]:
    return {
        "type": "learning",
        "topic": conversation_messages.splitlines()[0][:120] if conversation_messages else "",
        "project_context": "",
        "key_takeaways": [],
        "aha_moments": [],
    }


class DetailExtractor:
    def __init__(self):
        self._predict = None
        if dspy_available():
            dspy = get_dspy_module()
            self._predict = dspy.ChainOfThought(GenericTypeExtractor)

    def forward(self, conversation_type: str, conversation_messages: str, context_metadata: Dict[str, Any]) -> Dict[str, Any]:
        if self._predict:
            try:
                result = self._predict(
                    conversation_messages=conversation_messages,
                    conversation_type=conversation_type,
                    context_metadata=json.dumps(context_metadata),
                )
                parsed = json.loads(result.payload_json)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        if conversation_type == "debugging":
            return _extract_debugging_heuristic(conversation_messages)
        if conversation_type == "brainstorming":
            return _extract_brainstorming_heuristic(conversation_messages)
        if conversation_type == "code_review":
            return _extract_code_review_heuristic(conversation_messages)
        return _extract_learning_heuristic(conversation_messages)
