from __future__ import annotations

import inspect
import logging
import re
from collections.abc import Iterable
from typing import Any

from core.agents.pii_scrubber.prompts import build_pii_scrubber_prompt

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(
    r"(?<![\w])(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?![\w])"
)
CREDENTIAL_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|passwd|pwd|credential|access[_-]?key)\b\s*[:=]\s*[^\s,;]+"
)
BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{12,}")
KEY_RE = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,})\b")
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I)
INTERNAL_PATH_RE = re.compile(
    r"(?:(?:/Users|/home|/var/folders|/private/var|/Volumes)/[^\s:;,)]+|[A-Za-z]:\\Users\\[^\s:;,)]+)"
)
URL_RE = re.compile(r"\b(?:(?:https?|ftp)://|www\.)[^\s<>)\"']+", re.IGNORECASE)
LOCAL_TECH_URL_RE = re.compile(
    r"^(?:(?:https?|ws|redis|postgres|mysql)://)?(?:localhost|127(?:\.\d{1,3}){3}|0\.0\.0\.0|::1)(?::\d+)?(?:/.*)?$",
    re.IGNORECASE,
)
REDIS_TECH_URL_RE = re.compile(r"^redis(?:s)?://(?:localhost|127\.0\.0\.1|redis)(?::\d+)?(?:/\d+)?$", re.I)


def _as_known_pii(known_pii: Iterable[str] | None) -> list[str]:
    values = []
    for value in known_pii or []:
        cleaned = str(value or "").strip()
        if cleaned:
            values.append(cleaned)
    return sorted(set(values), key=len, reverse=True)


def _redact_known_pii(text: str, known_pii: list[str]) -> str:
    cleaned = text
    for value in known_pii:
        cleaned = re.sub(re.escape(value), "[REDACTED]", cleaned, flags=re.IGNORECASE)
    return cleaned


def _redact_url(match: re.Match[str]) -> str:
    url = match.group(0).rstrip(".,;")
    suffix = match.group(0)[len(url) :]
    if LOCAL_TECH_URL_RE.match(url) or REDIS_TECH_URL_RE.match(url):
        return match.group(0)
    return f"[URL]{suffix}"


def _fallback_scrub(transcript: str, known_pii: list[str]) -> str:
    cleaned = _redact_known_pii(transcript, known_pii)
    cleaned = EMAIL_RE.sub("[EMAIL]", cleaned)
    cleaned = PHONE_RE.sub("[PHONE]", cleaned)
    cleaned = CREDENTIAL_RE.sub(lambda match: f"{match.group(1)}=[CREDENTIAL]", cleaned)
    cleaned = BEARER_RE.sub("Bearer [CREDENTIAL]", cleaned)
    cleaned = KEY_RE.sub("[CREDENTIAL]", cleaned)
    cleaned = UUID_RE.sub("[IDENTIFIER]", cleaned)
    cleaned = INTERNAL_PATH_RE.sub("[PATH]", cleaned)
    cleaned = URL_RE.sub(_redact_url, cleaned)
    return cleaned


async def _call_llm(llm: Any, transcript: str, known_pii: list[str]) -> str:
    prompt = build_pii_scrubber_prompt(transcript, known_pii)
    if hasattr(llm, "scrub_pii_transcript"):
        result = llm.scrub_pii_transcript(transcript=transcript, prompt=prompt, known_pii=known_pii)
    elif hasattr(llm, "complete"):
        result = llm.complete(prompt)
    elif hasattr(llm, "generate"):
        result = llm.generate(prompt)
    elif callable(llm):
        result = llm(prompt)
    else:
        raise TypeError("llm must be callable or expose scrub_pii_transcript, complete, or generate")

    if inspect.isawaitable(result):
        result = await result
    return str(result or "").strip()


def _warn_if_pii_remains(cleaned: str, known_pii: list[str]) -> None:
    findings: list[str] = []
    if EMAIL_RE.search(cleaned):
        findings.append("email")
    if PHONE_RE.search(cleaned):
        findings.append("phone")
    remaining_known = [value for value in known_pii if re.search(re.escape(value), cleaned, flags=re.IGNORECASE)]
    if remaining_known:
        findings.append("known_pii")
    if findings:
        logger.warning("pii_scrubber_residual_pii_detected", extra={"findings": findings})


async def scrub_pii_transcript(
    transcript: str,
    llm: Any | None = None,
    known_pii: Iterable[str] | None = None,
) -> str:
    pii_values = _as_known_pii(known_pii)
    source = str(transcript or "")
    if not source:
        return ""

    if llm is None:
        cleaned = _fallback_scrub(source, pii_values)
    else:
        try:
            cleaned = await _call_llm(llm, source, pii_values)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pii_scrubber_llm_failed_using_fallback", extra={"error": str(exc)})
            cleaned = _fallback_scrub(source, pii_values)

    cleaned = _redact_known_pii(cleaned, pii_values)
    cleaned = EMAIL_RE.sub("[EMAIL]", cleaned)
    cleaned = PHONE_RE.sub("[PHONE]", cleaned)
    _warn_if_pii_remains(cleaned, pii_values)
    return cleaned
