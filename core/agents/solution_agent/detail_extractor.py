from core.agents.llm_caller import call_llm_json

SYSTEM_PROMPT = """You are a solution detail extraction agent. Given an assistant message proposing a fix, extract the concrete implementation details.

Extract exactly:
- steps: Ordered list of concrete actions taken or proposed. Each step is one sentence. Empty list if not applicable.
- code_snippets: Exact code blocks from the assistant message that are part of the fix. Preserve formatting. Empty list if none.
- tools_used: Tools, commands, or packages explicitly mentioned (e.g. "npm install", "docker-compose up", "pip install httpx"). Empty list if none.
- canonical_label: 5-10 word precise label for this solution attempt. Include the fix type and target component. Example: "Add null check for findOne result in UserService"

Output JSON only:
{
  "canonical_label": "...",
  "steps": [...],
  "code_snippets": [...],
  "tools_used": [...]
}

SOLUTION EXCERPT:
{source_text}"""


async def run_detail_extractor(segment: dict) -> dict:
    return await call_llm_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=f"SOLUTION EXCERPT:\n{segment['source_text']}",
    )
