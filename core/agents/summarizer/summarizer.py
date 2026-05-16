from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from core.agents.extraction_outputs import (
    EnrichedProblem,
    ExtractedSolution,
    IssueAgentOutput,
    SolutionAgentOutput,
)
from core.agents.llm_caller import call_llm_json
from core.agents.summarizer.prompts import SUMMARIZER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


_RAW_LINE_RE = re.compile(r'(?i)(traceback|\bat\s+\S+\(|error:|exception:|```|\{\s*"|\[\s*\{)')


def _compact_whitespace(value: str) -> str:
    return " ".join(str(value or "").split())


def _clip_sentence(value: str, max_length: int = 190) -> str:
    text = _compact_whitespace(value)
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    clipped = text[: max_length - 1].rsplit(" ", 1)[0]
    return f"{clipped}..."


def _fallback_label(value: str) -> str:
    text = _compact_whitespace(value)
    text = re.sub(r"[`*_#>\\[\\]{}()]+", " ", text)
    words = [word.strip(".,:;!?") for word in text.split() if word.strip(".,:;!?")]
    label = " ".join(words[:6]).strip()
    return label[:72].strip() or "Stored memory node"


def _fallback_summary(value: str) -> str:
    lines = [
        _compact_whitespace(line)
        for line in str(value or "").splitlines()
        if line.strip() and not _RAW_LINE_RE.search(line)
    ]
    return _clip_sentence(" ".join(lines) or value)


def _clean_result(result: dict[str, Any], fallback_text: str) -> dict[str, str]:
    label = _compact_whitespace(str(result.get("display_label") or ""))
    summary = _compact_whitespace(str(result.get("display_summary") or ""))
    if not label:
        label = _fallback_label(fallback_text)
    if not summary:
        summary = _fallback_summary(fallback_text)
    return {
        "display_label": _fallback_label(label),
        "display_summary": _fallback_summary(summary),
    }


async def summarize_node_display(node_type: str, label: str, description: str) -> dict[str, str]:
    fallback_text = f"{label}. {description}".strip()
    user_content = json.dumps(
        {
            "type": node_type,
            "canonical_label": label,
            "description": description,
        },
        ensure_ascii=True,
    )
    try:
        result = await call_llm_json(SUMMARIZER_SYSTEM_PROMPT, user_content)
        return _clean_result(result, fallback_text)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "summarizer_failed_using_fallback",
            extra={"node_type": node_type, "label": label, "error": str(exc)},
        )
        return _clean_result({}, fallback_text)


async def _summarize_problem(problem: EnrichedProblem) -> EnrichedProblem:
    raw_description = problem.raw_description or problem.description
    display = await summarize_node_display("Problem", problem.canonical_label, raw_description)
    return problem.model_copy(
        update={
            "display_label": display["display_label"],
            "display_summary": display["display_summary"],
            "raw_description": raw_description,
        }
    )


async def _summarize_solution(solution: ExtractedSolution) -> ExtractedSolution:
    raw_description = solution.raw_description or solution.in_depth_summary or solution.description
    display = await summarize_node_display("Solution", solution.canonical_label, raw_description)
    return solution.model_copy(
        update={
            "display_label": display["display_label"],
            "display_summary": display["display_summary"],
            "raw_description": raw_description,
        }
    )


async def summarize_extraction_outputs(
    issue_output: IssueAgentOutput,
    solution_output: SolutionAgentOutput,
) -> tuple[IssueAgentOutput, SolutionAgentOutput]:
    problems, solutions = await asyncio.gather(
        asyncio.gather(*[_summarize_problem(problem) for problem in issue_output.problems]),
        asyncio.gather(*[_summarize_solution(solution) for solution in solution_output.solutions]),
    )
    return (
        issue_output.model_copy(update={"problems": list(problems)}),
        solution_output.model_copy(update={"solutions": list(solutions)}),
    )
