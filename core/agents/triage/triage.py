from __future__ import annotations

import logging
import re

from core.agents.extraction_outputs import TriageDecision
from core.agents.llm_caller import call_llm_json
from core.agents.triage.prompts import TRIAGE_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_LOW_SIGNAL_PATTERNS = (
    r"\breverse a string\b",
    r"\bhello\b",
    r"\bhi\b",
    r"\bthanks?\b",
    r"\bwhat is orange\b",
)

_DURABLE_SIGNAL_PATTERNS = (
    r"\berror\b",
    r"\bfailed?\b",
    r"\bnot working\b",
    r"\bbroke\b",
    r"\bfixed?\b",
    r"\bresolved?\b",
    r"\broot cause\b",
    r"\bcompatib",
    r"\btried\b",
    r"\bevaluat",
    r"\babandoned\b",
    r"\bpartial\b",
    r"\bwe use\b",
    r"\bour compan(?:y|ies)\b",
    r"\bcompany uses\b",
    r"\buse \.md\b",
    r"\bmarkdown\b",
    r"\bprefer\b",
    r"\bshould\b",
    r"\bmake (?:it|the site|the website)\b",
    r"\bsteering\b",
    r"\bfact\b",
    r"\bdecision\b",
    r"\boutcome\b",
    r"\bconstraint\b",
    r"\blesson\b",
    r"\bremember\b",
    r"\bstore\b",
)


_GENERIC_TASK_PATTERNS = (
    r"\bcreate (?:a )?(?:website|site|app|landing page)\b",
    r"\bbuild (?:a )?(?:website|site|app|landing page)\b",
)

_STEERING_PATTERNS = (
    r"\bmake (?:it|the site|the website)\b",
    r"\bshould feel\b",
    r"\buse (?:linear|vercel|apple)\b",
    r"\bdarker\b",
    r"\blighter\b",
    r"\bcopy tone\b",
    r"\brequired fields?\b",
    r"\bonly use\b",
    r"\bprefer\b",
)

_ORG_FACT_PATTERNS = (
    r"\bour compan(?:y|ies)\b",
    r"\bcompany uses\b",
    r"\bwe use\b",
    r"\bwe store\b",
    r"\bmemory source\b",
    r"\baws glue\b",
    r"\bglue issue\b",
    r"\bin our org\b",
    r"\bour team\b",
    r"\bgo[- ]to[- ]market\b",
    r"\bgtm\b",
    r"\bsoft launch\b",
    r"\bpaid ads?\b",
    r"\binbound\b",
    r"\binvestors?\b",
    r"\bseries a\b",
    r"\bpricing\b",
    r"\bdistribution\b",
)


def _fallback_triage(transcript: str, *, company: str | None = None) -> TriageDecision:
    lowered = transcript.lower()
    if len(lowered.split()) < 32 and any(re.search(pattern, lowered) for pattern in _LOW_SIGNAL_PATTERNS):
        return TriageDecision(should_store=False, suggested_scope="user", confidence=0.85, reason="Conversation was a low-signal generic exchange.")
    if any(re.search(pattern, lowered) for pattern in _GENERIC_TASK_PATTERNS) and not any(
        re.search(pattern, lowered) for pattern in _STEERING_PATTERNS
    ):
        return TriageDecision(should_store=False, suggested_scope="user", confidence=0.78, reason="Generic execution request without durable steering.")

    has_org_signal = any(re.search(pattern, lowered) for pattern in _ORG_FACT_PATTERNS)
    has_user_signal = any(re.search(pattern, lowered) for pattern in _STEERING_PATTERNS)
    suggested_scope = "both" if has_org_signal and has_user_signal else "global" if has_org_signal else "user"
    if any(re.search(pattern, lowered) for pattern in _DURABLE_SIGNAL_PATTERNS):
        confidence = 0.74 if suggested_scope == "user" or (company or "").strip() else 0.58
        return TriageDecision(
            should_store=True,
            suggested_scope=suggested_scope,
            confidence=confidence,
            reason="Conversation contains durable memory signals.",
        )
    return TriageDecision(should_store=False, suggested_scope="user", confidence=0.72, reason="No durable decision, outcome, preference, constraint, or lesson was evident.")


async def run_triage_agent(transcript: str, *, scope: str | None = None, company: str | None = None) -> TriageDecision:
    user_content = f"Company/org: {company or 'unknown'}\nRequested scope override: {scope or 'none'}\n\nTranscript:\n{transcript}"
    try:
        result = await call_llm_json(TRIAGE_AGENT_SYSTEM_PROMPT, user_content)
        decision = TriageDecision.model_validate(result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("triage_agent_fallback", extra={"error": str(exc)})
        decision = _fallback_triage(transcript, company=company)

    if scope in {"user", "global", "both"}:
        decision.suggested_scope = scope

    logger.info(
        "triage_decision",
        extra={
            "suggested_scope": decision.suggested_scope,
            "company": company,
            "should_store": decision.should_store,
            "confidence": decision.confidence,
            "low_confidence": decision.low_confidence,
            "reason": decision.reason,
        },
    )
    return decision
