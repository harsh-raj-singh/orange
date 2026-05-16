import json

from core.agents.extraction_outputs import EnrichedProblem
from core.agents.issue_agent.prompts import PROBLEM_RELATIONSHIP_SYSTEM_PROMPT
from core.agents.llm_caller import call_llm_json


async def run_relationship_agent(
    problems: list[EnrichedProblem],
    transcript: str,
) -> list[EnrichedProblem]:
    problems_json = json.dumps(
        [
            {
                "segment_id": p.segment_id,
                "canonical_label": p.canonical_label,
                "first_seen_turn": p.first_seen_turn,
                "description": p.description,
            }
            for p in problems
        ]
    )

    result = await call_llm_json(
        system_prompt=PROBLEM_RELATIONSHIP_SYSTEM_PROMPT,
        user_content=f"PROBLEMS:\n{problems_json}\n\nFULL TRANSCRIPT:\n{transcript}",
    )

    rel_map = {item["segment_id"]: item for item in result}

    for problem in problems:
        if problem.segment_id in rel_map:
            relationship = rel_map[problem.segment_id]
            problem.parent_segment_id = relationship.get("parent_segment_id")
            problem.relationship_to_parent = relationship.get("relationship_to_parent")
            problem.via_solution_label = relationship.get("via_solution_label")
            problem.depth = relationship.get("depth", 0)

    return problems
