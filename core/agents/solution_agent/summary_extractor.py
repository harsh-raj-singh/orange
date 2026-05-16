from core.agents.llm_caller import call_llm_json
from core.agents.solution_agent.prompts import SOLUTION_SUMMARY_SYSTEM_PROMPT


async def run_summary_extractor(segment: dict, detail: dict, outcome: dict) -> dict:
    user_content = f"""SOLUTION:
{segment['source_text']}

OUTCOME: {outcome.get('outcome')}
FAILURE REASON: {outcome.get('failure_reason')}
STEPS: {detail.get('steps')}
CODE CHANGES: {detail.get('code_snippets')}"""

    return await call_llm_json(
        system_prompt=SOLUTION_SUMMARY_SYSTEM_PROMPT,
        user_content=user_content,
    )
