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
)


def _fallback_triage(transcript: str) -> TriageDecision:
    lowered = transcript.lower()
    if len(lowered.split()) < 32 and any(re.search(pattern, lowered) for pattern in _LOW_SIGNAL_PATTERNS):
        return TriageDecision(worth_storing=False, reason="Conversation was a low-signal generic exchange.")
    if any(re.search(pattern, lowered) for pattern in _DURABLE_SIGNAL_PATTERNS):
        return TriageDecision(worth_storing=True, reason="Conversation contains durable debugging or evaluation signals.")
    return TriageDecision(worth_storing=False, reason="No concrete technical learning was evident.")


async def run_triage_agent(transcript: str) -> TriageDecision:
    try:
        result = await call_llm_json(TRIAGE_AGENT_SYSTEM_PROMPT, transcript)
        decision = TriageDecision.model_validate(result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("triage_agent_fallback", extra={"error": str(exc)})
        decision = _fallback_triage(transcript)

    logger.info(
        "triage_decision",
        extra={"worth_storing": decision.worth_storing, "reason": decision.reason},
    )
    return decision
