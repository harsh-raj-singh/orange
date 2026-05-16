from __future__ import annotations

import logging
import re

from core.agents.extraction_outputs import TriageDecision
from core.agents.llm_caller import call_llm_json
from core.agents.triage.prompts import GLOBAL_TRIAGE_AGENT_SYSTEM_PROMPT, USER_TRIAGE_AGENT_SYSTEM_PROMPT

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
)


def _fallback_triage(transcript: str, *, scope: str = "user", company: str | None = None) -> TriageDecision:
    lowered = transcript.lower()
    if scope == "global":
        if not (company or "").strip():
            return TriageDecision(worth_storing=False, reason="No company identity was supplied for shared memory.")
        if any(re.search(pattern, lowered) for pattern in _ORG_FACT_PATTERNS):
            return TriageDecision(worth_storing=True, reason="Conversation includes a user-stated company fact.")
        return TriageDecision(worth_storing=False, reason="No company-scoped shared fact was evident.")

    if len(lowered.split()) < 32 and any(re.search(pattern, lowered) for pattern in _LOW_SIGNAL_PATTERNS):
        return TriageDecision(worth_storing=False, reason="Conversation was a low-signal generic exchange.")
    if any(re.search(pattern, lowered) for pattern in _GENERIC_TASK_PATTERNS) and not any(
        re.search(pattern, lowered) for pattern in _STEERING_PATTERNS
    ):
        return TriageDecision(worth_storing=False, reason="Generic execution request without durable steering.")
    if any(re.search(pattern, lowered) for pattern in _DURABLE_SIGNAL_PATTERNS):
        return TriageDecision(worth_storing=True, reason="Conversation contains durable memory signals.")
    return TriageDecision(worth_storing=False, reason="No concrete technical learning was evident.")


async def run_triage_agent(transcript: str, *, scope: str = "user", company: str | None = None) -> TriageDecision:
    system_prompt = GLOBAL_TRIAGE_AGENT_SYSTEM_PROMPT if scope == "global" else USER_TRIAGE_AGENT_SYSTEM_PROMPT
    user_content = f"Company/org: {company or 'unknown'}\n\nTranscript:\n{transcript}" if scope == "global" else transcript
    try:
        result = await call_llm_json(system_prompt, user_content)
        decision = TriageDecision.model_validate(result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("triage_agent_fallback", extra={"error": str(exc)})
        decision = _fallback_triage(transcript, scope=scope, company=company)

    logger.info(
        "triage_decision",
        extra={"scope": scope, "company": company, "worth_storing": decision.worth_storing, "reason": decision.reason},
    )
    return decision
