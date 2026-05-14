from core.agents.llm_caller import call_llm_json

SYSTEM_PROMPT = """You are a solution outcome extraction agent. Given a solution attempt and the conversation that followed it, determine the outcome.

Outcome must be exactly one of:
- "success": The user confirmed the fix worked and the problem is resolved
- "partial": The fix helped but did not fully resolve the problem
- "failed": The user tried it and it did not work at all
- "caused_new_problem": The fix introduced a new distinct error
- "untried": There is no user message after this solution indicating they tried it

Also extract:
- failure_reason: If outcome is failed or caused_new_problem, why did it fail? null otherwise.
- failure_error_code: If caused_new_problem, the new error code introduced. null otherwise.
- partial_fix_description: If partial, what did it fix? null otherwise.

Output JSON only:
{
  "outcome": "...",
  "failure_reason": null,
  "failure_error_code": null,
  "partial_fix_description": null
}

SOLUTION ATTEMPT:
{source_text}

CONVERSATION AFTER THIS SOLUTION:
{followup_text}"""


async def run_outcome_extractor(segment: dict, followup_text: str) -> dict:
    return await call_llm_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=f"SOLUTION ATTEMPT:\n{segment['source_text']}\n\nCONVERSATION AFTER THIS SOLUTION:\n{followup_text}",
    )
