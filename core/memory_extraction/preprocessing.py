from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List

CRITICAL_PATTERNS = [
    r"exception",
    r"error",
    r"traceback",
    r"accessdenied",
    r"forbidden",
    r"failed",
    r"didn't work",
    r"doesn't work",
    r"fixed",
    r"worked",
]

CODE_LANG_PATTERN = re.compile(r"```([a-zA-Z0-9_+-]+)")


def detect_languages(messages: List[Dict[str, Any]]) -> List[str]:
    langs = set()
    for msg in messages:
        for m in CODE_LANG_PATTERN.findall(msg.get("content", "")):
            langs.add(m.lower())
    return sorted(langs)


def estimate_duration_minutes(messages: List[Dict[str, Any]]) -> int:
    timestamps = []
    for msg in messages:
        ts = msg.get("timestamp")
        if not ts:
            continue
        try:
            timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
        except Exception:
            continue
    if len(timestamps) < 2:
        return 0
    delta = max(timestamps) - min(timestamps)
    return max(0, int(delta.total_seconds() // 60))


def build_conversation_text(messages: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    lines = []
    for idx, msg in enumerate(messages, start=1):
        role = msg.get("role", "unknown")
        content = (msg.get("content", "") or "").strip()
        lines.append(f"[{idx}] {role}: {content}")

    joined = "\n".join(lines)
    if len(joined) <= max_chars:
        return joined

    critical = []
    for line in lines:
        low = line.lower()
        if any(re.search(pat, low) for pat in CRITICAL_PATTERNS):
            critical.append(line)

    if not critical:
        return joined[:max_chars]

    merged = "\n".join(critical)
    if len(merged) > max_chars:
        return merged[:max_chars]

    tail = joined[max(0, len(joined) - (max_chars - len(merged) - 1)) :]
    return f"{merged}\n{tail}"[:max_chars]


def preprocess_chat(chat: Dict[str, Any]) -> Dict[str, Any]:
    messages = chat.get("messages", [])
    return {
        "conversation": build_conversation_text(messages),
        "metadata": {
            "turns": len(messages) // 2,
            "duration_minutes": estimate_duration_minutes(messages),
            "languages_detected": detect_languages(messages),
            "memory_request_reason": chat.get("memory_request_reason") or "",
            "memory_request_aspects": chat.get("memory_request_aspects") or [],
        },
    }
