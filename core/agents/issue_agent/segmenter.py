from core.agents.extraction_outputs import RawProblemSegment
from core.agents.issue_agent.prompts import ISSUE_SEGMENTER_SYSTEM_PROMPT
from core.agents.llm_caller import call_llm_json


async def run_segmenter(transcript: str) -> list[RawProblemSegment]:
    result = await call_llm_json(
        system_prompt=ISSUE_SEGMENTER_SYSTEM_PROMPT,
        user_content=f"TRANSCRIPT:\n{transcript}",
    )
    return [RawProblemSegment(**item) for item in result]
