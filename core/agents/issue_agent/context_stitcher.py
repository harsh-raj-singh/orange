import json

from core.agents.extraction_outputs import EnrichedProblem, SolutionAgentOutput
from core.agents.issue_agent.prompts import CONTEXT_STITCHER_SYSTEM_PROMPT
from core.agents.llm_caller import call_llm_json


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
        system_prompt=CONTEXT_STITCHER_SYSTEM_PROMPT,
        user_content=f"PROBLEMS:\n{problems_json}\n\nSOLUTIONS:\n{solutions_json}",
    )

    context_map = {item["segment_id"]: item["prior_solution_contexts"] for item in result}

    for problem in problems:
        problem.prior_solution_contexts = context_map.get(problem.segment_id, [])

    return problems
