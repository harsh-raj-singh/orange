from core.agents.extraction_outputs import RawProblemSegment
from core.agents.llm_caller import call_llm_json

SYSTEM_PROMPT = """You are an error signature extraction agent. Given a transcript excerpt describing a programming error, extract the exact technical error signature.

Rules:
- error_code: The specific error code if explicitly present (e.g. "TS2344", "ECONNREFUSED", "E11000", "404"). null if not present - do not guess.
- error_type: The error class or category explicitly named (e.g. "TypeError", "MongoServerError", "SyntaxError", "NullPointerException"). null if not present.
- stack_trace_summary: Copy the first 2-3 most informative lines of any stack trace verbatim. null if no stack trace present.
- Only extract what is explicitly written. Never infer or guess.
- Output JSON only: {"error_code": ..., "error_type": ..., "stack_trace_summary": ...}"""


async def run_error_signature(segment: RawProblemSegment) -> dict:
    return await call_llm_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=f"EXCERPT:\n{segment.source_text}",
    )
