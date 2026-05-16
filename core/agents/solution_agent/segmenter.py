from core.agents.llm_caller import call_llm_json
from core.agents.solution_agent.prompts import SOLUTION_SEGMENTER_SYSTEM_PROMPT


async def run_solution_segmenter(transcript: str) -> list[dict]:
    result = await call_llm_json(
        system_prompt=SOLUTION_SEGMENTER_SYSTEM_PROMPT,
        user_content=f"TRANSCRIPT:\n{transcript}",
    )
    return result if isinstance(result, list) else []
