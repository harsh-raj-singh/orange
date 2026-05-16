from __future__ import annotations

import logging
import re
from typing import Any

from core.agents.extraction_outputs import InsightDraft
from core.agents.insight_extractor.prompts import INSIGHT_EXTRACTOR_SYSTEM_PROMPT
from core.agents.llm_caller import call_llm_json

logger = logging.getLogger(__name__)

_OUTCOMES = {"resolved", "exploratory", "partial", "abandoned"}


def _compact_label(text: str, fallback: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9+#.-]+", text)[:8]
    label = " ".join(tokens).strip()
    return label or fallback


def _tags_from(transcript: str) -> list[str]:
    candidates = [
        "fastapi",
        "cors",
        "oauth",
        "passport",
        "express",
        "redis",
        "sqlalchemy",
        "rapidfuzz",
        "address-matching",
        "chroma",
        "neo4j",
        "railway",
        "vercel",
        "next.js",
        "typescript",
    ]
    lowered = transcript.lower()
    return [tag for tag in candidates if tag in lowered][:6]


def _fallback_insights(transcript: str) -> list[InsightDraft]:
    lowered = transcript.lower()
    tags = _tags_from(transcript)
    if "reverse a string" in lowered and "error" not in lowered and "failed" not in lowered:
        return []

    outcome = "exploratory"
    if any(token in lowered for token in ("fixed", "resolved", "worked", "success")):
        outcome = "resolved"
    elif any(token in lowered for token in ("partial", "still failing", "still broken")):
        outcome = "partial"
    elif any(token in lowered for token in ("abandoned", "dropped", "do not retry")):
        outcome = "abandoned"

    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", transcript) if part.strip()]
    what = sentences[0][:240] if sentences else transcript[:240]
    how = next((s[:240] for s in sentences if re.search(r"\b(fixed|resolved|tried|updated|downgraded|used)\b", s, re.I)), None)
    why = next((s[:240] for s in sentences if re.search(r"\b(root cause|because|due to|incompatib)\b", s, re.I)), None)
    label_source = how or what
    label = _compact_label(label_source, "Developer session insight")
    return [
        InsightDraft(
            what=what,
            why=why,
            how=how,
            outcome=outcome,
            tags=tags,
            display_label=label,
            display_summary=(how or what)[:260],
        )
    ]


def _normalize_item(item: dict[str, Any]) -> InsightDraft | None:
    try:
        draft = InsightDraft.model_validate(item)
    except Exception:
        return None
    if draft.outcome not in _OUTCOMES:
        draft.outcome = "exploratory"
    draft.tags = [str(tag).strip() for tag in draft.tags if str(tag).strip()]
    return draft


async def extract_insights(transcript: str) -> list[InsightDraft]:
    try:
        result = await call_llm_json(INSIGHT_EXTRACTOR_SYSTEM_PROMPT, transcript)
        raw_items = result if isinstance(result, list) else result.get("insights", [])
        insights = [_normalize_item(item) for item in raw_items if isinstance(item, dict)]
        drafts = [insight for insight in insights if insight is not None]
    except Exception as exc:  # noqa: BLE001
        logger.warning("insight_extractor_fallback", extra={"error": str(exc)})
        drafts = _fallback_insights(transcript)

    logger.info(
        "insight_extractor_output",
        extra={"insight_count": len(drafts), "labels": [draft.display_label for draft in drafts]},
    )
    return drafts
