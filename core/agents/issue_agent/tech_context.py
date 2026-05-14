from core.agents.extraction_outputs import RawProblemSegment
from core.agents.llm_caller import call_llm_json

SYSTEM_PROMPT = """You are a technical context extraction agent. Given a debugging transcript excerpt, extract the technical environment.

Rules:
- tech_stack: List only technologies explicitly named - include version numbers if stated (e.g. ["TypeScript 5.2", "NestJS 10", "PostgreSQL 15"]). Empty list if none mentioned.
- affected_file_paths: File paths or module names explicitly mentioned in the error or user message (e.g. ["src/repositories/user.repository.ts", "core/db.py"]). Empty list if none.
- Do not infer. If the user says "my database" without naming it, do not add "PostgreSQL".
- Output JSON only: {"tech_stack": [...], "affected_file_paths": [...]}"""


async def run_tech_context(segment: RawProblemSegment) -> dict:
    return await call_llm_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=f"EXCERPT:\n{segment.source_text}\nRELEVANT TURNS: {segment.relevant_turns}",
    )
