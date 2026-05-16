import json
from collections import defaultdict

from core.agents.extraction_outputs import ExtractedSolution
from core.agents.llm_caller import call_llm_json
from core.agents.solution_agent.prompts import SOLUTION_RELATIONSHIP_SYSTEM_PROMPT


def _parse_pairwise_refinements(result: object, expected_len: int) -> list[bool]:
    if expected_len <= 0:
        return []

    values: list[object] = []
    if isinstance(result, dict):
        candidate = result.get("pairwise_refinements")
        if isinstance(candidate, list):
            values = candidate
    elif isinstance(result, list):
        values = result

    parsed = [bool(v) if isinstance(v, bool) else False for v in values[:expected_len]]
    if len(parsed) < expected_len:
        parsed.extend([False] * (expected_len - len(parsed)))
    return parsed


async def _run_solution_relationship_agent(
    solutions: list[ExtractedSolution],
) -> list[ExtractedSolution]:
    grouped_indices: dict[str, list[int]] = defaultdict(list)
    for idx, solution in enumerate(solutions):
        grouped_indices[solution.addresses_problem_label].append(idx)

    for indices in grouped_indices.values():
        for attempt_idx, sol_idx in enumerate(indices, start=1):
            solutions[sol_idx].attempt_number = attempt_idx
            solutions[sol_idx].parent_solution_label = None

        if len(indices) <= 1:
            continue

        ordered_group = [solutions[i] for i in indices]
        attempts_payload = json.dumps(
            [
                {
                    "attempt_number": i + 1,
                    "canonical_label": s.canonical_label,
                    "description": s.description,
                    "in_depth_summary": s.in_depth_summary,
                    "steps": s.steps,
                    "applied_turn": s.applied_turn,
                    "turn_sequence": s.turn_sequence,
                    "outcome": s.outcome.value,
                }
                for i, s in enumerate(ordered_group)
            ]
        )

        result = await call_llm_json(
            system_prompt=SOLUTION_RELATIONSHIP_SYSTEM_PROMPT,
            user_content=(
                f"PROBLEM LABEL: {ordered_group[0].addresses_problem_label}\n"
                f"ORDERED ATTEMPTS:\n{attempts_payload}"
            ),
        )

        pairwise_refinements = _parse_pairwise_refinements(result, expected_len=len(indices) - 1)
        for i, is_refinement in enumerate(pairwise_refinements, start=1):
            if is_refinement:
                child_idx = indices[i]
                parent_idx = indices[i - 1]
                solutions[child_idx].parent_solution_label = solutions[parent_idx].canonical_label

    return solutions
