from core.agents.extraction_outputs import RawProblemSegment
from core.agents.llm_caller import call_llm_json

SYSTEM_PROMPT = """You are a code extraction agent. Given a debugging transcript excerpt, extract the code snippets that are directly part of the problem.

Rules:
- Only extract code from the USER messages that shows the buggy/failing code.
- Do NOT extract solution code, suggested fixes, or assistant code.
- If the user pasted a large block, extract only the lines directly relevant to where the error occurs.
- Preserve exact formatting, indentation, and variable names.
- If multiple distinct snippets are relevant, include each as a separate string in the array.
- Output JSON only: {"relevant_code": [...]}
- Empty list if no code is present in the excerpt."""


async def run_code_snippet(segment: RawProblemSegment) -> dict:
    return await call_llm_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=f"EXCERPT:\n{segment.source_text}",
    )
