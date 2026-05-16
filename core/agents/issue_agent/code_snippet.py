from core.agents.extraction_outputs import RawProblemSegment
from core.agents.issue_agent.prompts import CODE_SNIPPET_SYSTEM_PROMPT
from core.agents.llm_caller import call_llm_json


async def run_code_snippet(segment: RawProblemSegment) -> dict:
    return await call_llm_json(
        system_prompt=CODE_SNIPPET_SYSTEM_PROMPT,
        user_content=f"EXCERPT:\n{segment.source_text}",
    )
