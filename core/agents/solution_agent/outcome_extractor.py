from core.agents.llm_caller import call_llm_json
from core.agents.solution_agent.prompts import SOLUTION_OUTCOME_SYSTEM_PROMPT


async def run_outcome_extractor(segment: dict, followup_text: str) -> dict:
    return await call_llm_json(
        system_prompt=SOLUTION_OUTCOME_SYSTEM_PROMPT,
        user_content=f"SOLUTION ATTEMPT:\n{segment['source_text']}\n\nCONVERSATION AFTER THIS SOLUTION:\n{followup_text}",
    )
