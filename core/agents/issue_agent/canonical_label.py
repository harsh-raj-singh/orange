from core.agents.extraction_outputs import RawProblemSegment
from core.agents.issue_agent.prompts import CANONICAL_LABEL_SYSTEM_PROMPT
from core.agents.llm_caller import call_llm_json


async def run_canonical_label(
    segment: RawProblemSegment,
    wave1: dict,
    solution_labels: list[str],
) -> dict:
    user_content = f"""PROBLEM EXCERPT: {segment.source_text}
ERROR CODE: {wave1.get('error_code')}
ERROR TYPE: {wave1.get('error_type')}
STACK TRACE: {wave1.get('stack_trace_summary')}
TECH STACK: {wave1.get('tech_stack')}
AFFECTED FILES: {wave1.get('affected_file_paths')}

The Solution Agent has referenced this problem using one of these labels:
{solution_labels}

Generate a canonical_label that exactly matches the most relevant one from this list if it clearly refers to the same problem. If none match, generate your own precise label using the error code and type."""

    return await call_llm_json(
        system_prompt=CANONICAL_LABEL_SYSTEM_PROMPT,
        user_content=user_content,
    )
