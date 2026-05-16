from core.agents.base_prompts import USER_SCOPE_EXTRACTION_PROMPT, global_scope_extraction_prompt

SOLUTION_AGENT_USER_SCOPE_PROMPT = USER_SCOPE_EXTRACTION_PROMPT
SOLUTION_AGENT_GLOBAL_SCOPE_PROMPT = global_scope_extraction_prompt("solution")

SOLUTION_SEGMENTER_SYSTEM_PROMPT = """You are a solution segmentation agent. Your only job is to identify distinct solution attempts made by the assistant in this debugging conversation.

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

SOLUTION_DETAIL_SYSTEM_PROMPT = """You are a solution detail extraction agent. Given an assistant message proposing a fix, extract the concrete implementation details.

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

SOLUTION_OUTCOME_SYSTEM_PROMPT = """You are a solution outcome extraction agent. Given a solution attempt and the conversation that followed it, determine the outcome.

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

SOLUTION_SUMMARY_SYSTEM_PROMPT = """You are a solution summary agent. Given a solution attempt and its outcome, write a detailed summary that will be stored as context for future debugging sessions.

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

SOLUTION_RELATIONSHIP_SYSTEM_PROMPT = """You are a solution relationship agent.

You will be given ordered solution attempts for the same problem label.
For each consecutive pair, decide whether the later attempt is:
- a refinement of the previous attempt (same approach, modified), or
- a fresh independent attempt (different approach).

Output JSON only in this format:
{"pairwise_refinements": [true, false]}

Rules:
- The boolean list length must be exactly N-1 where N is number of attempts.
- Index 0 corresponds to (attempt 2 vs attempt 1), index 1 to (attempt 3 vs attempt 2), etc.
- Use true only when the later attempt clearly modifies the same approach.
- If uncertain, use false.
"""
