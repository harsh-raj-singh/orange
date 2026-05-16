from core.agents.llm_caller import call_llm_json
from core.agents.solution_agent.prompts import SOLUTION_DETAIL_SYSTEM_PROMPT


async def run_detail_extractor(segment: dict) -> dict:
    return await call_llm_json(
        system_prompt=SOLUTION_DETAIL_SYSTEM_PROMPT,
        user_content=f"SOLUTION EXCERPT:\n{segment['source_text']}",
    )
