from core.agents.extraction_outputs import RawProblemSegment
from core.agents.llm_caller import call_llm_json

SYSTEM_PROMPT = """You are a problem segmentation agent. Your only job is to identify distinct problems or errors the USER encountered in this debugging conversation.

Rules:
- Only extract problems from USER messages. Ignore assistant messages entirely.
- A new problem is distinct if it has a different error, different root location, or occurs after a solution attempt changed the system state and produced a new error.
- If the user is clearly describing the same error across multiple messages, treat it as ONE problem with multiple turn numbers.
- Be conservative - fewer, well-defined problems is better than many vague ones.
- Output a JSON array. Each item must have exactly these keys: segment_id (string, "p1"/"p2"/etc), raw_description (string), relevant_turns (array of ints), source_text (exact user text that contains the problem).
- No explanation. JSON array only."""


async def run_segmenter(transcript: str) -> list[RawProblemSegment]:
    result = await call_llm_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=f"TRANSCRIPT:\n{transcript}",
    )
    return [RawProblemSegment(**item) for item in result]
