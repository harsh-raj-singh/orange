from core.agents.extraction_outputs import RawProblemSegment
from core.agents.llm_caller import call_llm_json

SYSTEM_PROMPT = """You are a problem labeling agent. Given a debugging problem and its extracted technical signature, generate a precise canonical label.

Rules for canonical_label:
- Must be specific enough to be unique and searchable
- 5-10 words maximum
- Include the error code if present (e.g. "TS2344 generic constraint mismatch in Repository<T>")
- Include the affected component or file if identifiable
- Bad examples: "TypeScript error", "database issue", "undefined error"
- Good examples: "TS2344 generic constraint mismatch in UserRepository", "ECONNREFUSED PostgreSQL connection failure on startup", "Cannot read property id of undefined in UserService.findById"

Rules for description:
- 2-4 sentences. What is the problem, where does it occur, what is the observed symptom.

Rules for llm_reasoning:
- 1-2 sentences. Why you identified this as a distinct problem worth storing as a separate node.

Output JSON only:
{"canonical_label": "...", "description": "...", "llm_reasoning": "..."}"""


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
        system_prompt=SYSTEM_PROMPT,
        user_content=user_content,
    )
