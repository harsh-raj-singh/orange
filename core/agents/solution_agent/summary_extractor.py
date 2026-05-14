from core.agents.llm_caller import call_llm_json

SYSTEM_PROMPT = """You are a solution summary agent. Given a solution attempt and its outcome, write a detailed summary that will be stored as context for future debugging sessions.

This summary will be the ONLY information available about this solution attempt when someone queries a related problem in a future session. Make it self-contained and complete.

The summary must include:
- What the solution attempted to do (precise technical description)
- The exact code changes or steps involved
- The outcome and why (if known)
- What it fixed, even partially
- What it did NOT fix or what new problem it caused

Write 3-6 sentences. Be specific - include file names, function names, error codes if relevant.
Do not be vague. "Fixed the issue" is not acceptable. "Added null check after userRepository.findOne() in UserService.findById() at line 34, preventing TypeError when user is not found" is acceptable.

Output JSON only: {"description": "...", "in_depth_summary": "..."}
- description: 1-2 sentence summary for quick scanning
- in_depth_summary: full 3-6 sentence detailed summary

SOLUTION:
{source_text}

OUTCOME: {outcome}
FAILURE REASON: {failure_reason}
STEPS: {steps}
CODE CHANGES: {code_snippets}"""


async def run_summary_extractor(segment: dict, detail: dict, outcome: dict) -> dict:
    user_content = f"""SOLUTION:
{segment['source_text']}

OUTCOME: {outcome.get('outcome')}
FAILURE REASON: {outcome.get('failure_reason')}
STEPS: {detail.get('steps')}
CODE CHANGES: {detail.get('code_snippets')}"""

    return await call_llm_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=user_content,
    )
