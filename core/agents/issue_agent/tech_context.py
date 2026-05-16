from core.agents.extraction_outputs import RawProblemSegment
from core.agents.issue_agent.prompts import TECH_CONTEXT_SYSTEM_PROMPT
from core.agents.llm_caller import call_llm_json


async def run_tech_context(segment: RawProblemSegment) -> dict:
    return await call_llm_json(
        system_prompt=TECH_CONTEXT_SYSTEM_PROMPT,
        user_content=f"EXCERPT:\n{segment.source_text}\nRELEVANT TURNS: {segment.relevant_turns}",
    )
