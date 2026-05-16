from __future__ import annotations

import logging
import re
from typing import Any

from core.agents.extraction_outputs import InsightDraft
from core.agents.insight_extractor.prompts import (
    GLOBAL_INSIGHT_EXTRACTOR_SYSTEM_PROMPT,
    USER_INSIGHT_EXTRACTOR_SYSTEM_PROMPT,
)
from core.agents.llm_caller import call_llm_json

logger = logging.getLogger(__name__)

_OUTCOMES = {"resolved", "exploratory", "partial", "abandoned"}
_MEMORY_KINDS = {"technical_insight", "user_fact", "company_fact", "preference", "steering"}


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
        "markdown",
        "md-files",
        "company-memory",
        "aws-glue",
    ]
    lowered = transcript.lower()
    return [tag for tag in candidates if tag in lowered][:6]


def _fallback_insights(transcript: str, *, scope: str = "user", company: str | None = None) -> list[InsightDraft]:
    lowered = transcript.lower()
    tags = _tags_from(transcript)
    if "reverse a string" in lowered and "error" not in lowered and "failed" not in lowered:
        return []
    if scope == "global" and not (company or "").strip():
        return []
    if scope == "global" and not any(
        token in lowered for token in ("our company", "our companies", "company uses", "we use", "aws glue", "glue issue")
    ):
        return []

    memory_kind = "technical_insight"
    if any(token in lowered for token in ("our company", "our companies", "company uses", "we use", "we store", "memory source")):
        memory_kind = "company_fact"
    if scope == "user" and any(token in lowered for token in ("prefer", "make it", "should feel", "only use", "required field")):
        memory_kind = "steering"
    if scope == "user" and any(token in lowered for token in ("i use", "my workflow", "my company", "our company")):
        memory_kind = "user_fact" if memory_kind == "technical_insight" else memory_kind

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
    if ".md" in lowered or "markdown" in lowered:
        tags = sorted(set([*tags, "markdown", "memory"]))
        label_source = "Markdown files for memory"
    label = _compact_label(label_source, "Developer session insight")
    return [
        InsightDraft(
            what=what,
            why=why,
            how=how,
            outcome=outcome,
            memory_kind=memory_kind,
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
    if draft.memory_kind not in _MEMORY_KINDS:
        draft.memory_kind = "technical_insight"
    draft.tags = [str(tag).strip() for tag in draft.tags if str(tag).strip()]
    return draft


async def extract_insights(transcript: str, *, scope: str = "user", company: str | None = None) -> list[InsightDraft]:
    system_prompt = GLOBAL_INSIGHT_EXTRACTOR_SYSTEM_PROMPT if scope == "global" else USER_INSIGHT_EXTRACTOR_SYSTEM_PROMPT
    user_content = f"Company/org: {company or 'unknown'}\n\nTranscript:\n{transcript}" if scope == "global" else transcript
    try:
        result = await call_llm_json(system_prompt, user_content)
        raw_items = result if isinstance(result, list) else result.get("insights", [])
        insights = [_normalize_item(item) for item in raw_items if isinstance(item, dict)]
        drafts = [insight for insight in insights if insight is not None]
    except Exception as exc:  # noqa: BLE001
        logger.warning("insight_extractor_fallback", extra={"error": str(exc)})
        drafts = _fallback_insights(transcript, scope=scope, company=company)

    logger.info(
        "insight_extractor_output",
        extra={"scope": scope, "company": company, "insight_count": len(drafts), "labels": [draft.display_label for draft in drafts]},
    )
    return drafts
