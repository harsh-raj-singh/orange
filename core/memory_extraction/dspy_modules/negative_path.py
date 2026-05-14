from __future__ import annotations

import json
from typing import Any, Dict, List

from .signatures import NegativePathSignature, dspy_available, get_dspy_module


FAILURE_MARKERS = ["didn't work", "doesn't work", "failed", "same error", "still broken", "not working"]


class NegativePathCapture:
    def __init__(self):
        self._predict = None
        if dspy_available():
            dspy = get_dspy_module()
            self._predict = dspy.Predict(NegativePathSignature)

    def forward(self, conversation_messages: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self._predict:
            try:
                result = self._predict(
                    conversation_messages=conversation_messages,
                    payload_json=json.dumps(payload),
                )
                parsed = json.loads(result.failed_solutions_json)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass

        lines = conversation_messages.splitlines()
        failed = []
        for idx, line in enumerate(lines):
            if "] assistant:" not in line:
                continue
            suggestion = line.split(":", 1)[-1].strip()
            if idx + 1 >= len(lines):
                continue
            nxt = lines[idx + 1].lower()
            if "] user:" in nxt and any(marker in nxt for marker in FAILURE_MARKERS):
                failed.append(
                    {
                        "suggested_by": "assistant",
                        "solution": suggestion,
                        "tried": True,
                        "result": lines[idx + 1].split(":", 1)[-1].strip(),
                        "why_failed": "User reported failure after trying suggestion",
                        "learning": "Do not prioritize this suggestion for the same context",
                    }
                )
        return failed
