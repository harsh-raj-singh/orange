from core.agents.llm_caller import call_llm_json

SYSTEM_PROMPT = """You are a solution segmentation agent. Your only job is to identify distinct solution attempts made by the assistant in this debugging conversation.

Rules:
- Only extract solutions from ASSISTANT messages. Ignore user messages entirely.
- A solution attempt is a concrete suggestion, fix, or code change proposed to address a problem.
- General explanations without a concrete fix are NOT solution attempts.
- If the assistant proposes multiple independent fixes in one message, treat each as a separate solution.
- If the assistant refines a previous suggestion in a follow-up message, treat it as a new attempt with parent_solution_label set.
- Set parent_solution_label to the segment_id of the solution this refines if it's a follow-up modification of a previous attempt on the same problem. Set to null if it's a fresh independent attempt.
- Output a JSON array. Each item must have exactly:
  {
    "segment_id": "s1",
    "raw_description": "brief description of what was proposed",
    "addresses_problem_description": "what user problem this is responding to",
    "relevant_turns": [2],
    "source_text": "exact assistant text containing the solution",
    "parent_solution_label": null
  }
- No explanation. JSON array only.

TRANSCRIPT:
{transcript}"""


async def run_solution_segmenter(transcript: str) -> list[dict]:
    result = await call_llm_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=f"TRANSCRIPT:\n{transcript}",
    )
    return result if isinstance(result, list) else []
