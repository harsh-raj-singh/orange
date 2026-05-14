import json

from core.agents.extraction_outputs import EnrichedProblem, SolutionAgentOutput
from core.agents.llm_caller import call_llm_json

SYSTEM_PROMPT = """You are a context stitching agent. Your job is to enrich each problem node with the complete history of solution attempts that preceded it.

For each problem, find all solutions that were applied BEFORE this problem's first_seen_turn. Write a cumulative prior_solution_contexts list - one string per solution attempt, ordered oldest first.

Each string must contain:
- Attempt number and outcome (e.g. "Attempt 1 (FAILED):")
- What the solution tried to do (complete description)
- The full in_depth_summary of the solution
- Why it failed or what it partially fixed

Root problems (no parent, first in session) will have empty prior_solution_contexts.

Output JSON array, one entry per problem in the same order as input:
[{"segment_id": "p1", "prior_solution_contexts": []}]

Be thorough in the summaries - this context will be the only information available when this problem is retrieved in future sessions without graph traversal."""


async def run_context_stitcher(
    problems: list[EnrichedProblem],
    solution_output: SolutionAgentOutput,
) -> list[EnrichedProblem]:
    problems_json = json.dumps(
        [
            {
                "segment_id": p.segment_id,
                "canonical_label": p.canonical_label,
                "first_seen_turn": p.first_seen_turn,
                "parent_segment_id": p.parent_segment_id,
            }
            for p in problems
        ]
    )

    solutions_json = json.dumps(
        [
            {
                "canonical_label": s.canonical_label,
                "description": s.description,
                "in_depth_summary": s.in_depth_summary,
                "outcome": s.outcome,
                "failure_reason": s.failure_reason,
                "applied_turn": s.applied_turn,
                "addresses_problem_label": s.addresses_problem_label,
            }
            for s in solution_output.solutions
        ]
    )

    result = await call_llm_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=f"PROBLEMS:\n{problems_json}\n\nSOLUTIONS:\n{solutions_json}",
    )

    context_map = {item["segment_id"]: item["prior_solution_contexts"] for item in result}

    for problem in problems:
        problem.prior_solution_contexts = context_map.get(problem.segment_id, [])

    return problems
