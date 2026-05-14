import json

from core.agents.extraction_outputs import EnrichedProblem
from core.agents.llm_caller import call_llm_json

SYSTEM_PROMPT = """You are a problem relationship agent. Given a list of problems from a single debugging session, determine their hierarchical relationships.

Definitions - read carefully:
- CAUSED_BY: Problem B appeared AFTER a solution/fix was applied to Problem A, and that fix directly caused or exposed Problem B. The key signal is: a code change happened between A and B.
- TRIGGERED_BY: Problem B was discovered while investigating Problem A, with NO code change in between. The user just noticed a second issue while looking at the first.

For each problem output:
- parent_segment_id: segment_id of parent, or null if root
- relationship_to_parent: "CAUSED_BY" or "TRIGGERED_BY" or null
- via_solution_label: if CAUSED_BY, the canonical_label of the solution that caused it. null otherwise.
- depth: 0 for root, 1 for direct child, 2 for grandchild

Rules:
- A problem cannot be the parent of a problem that appeared before it (check first_seen_turn)
- One parent maximum per problem
- When in doubt, do not assign a parent

Output JSON array, one entry per problem in input order:
[{"segment_id": "p1", "parent_segment_id": null, "relationship_to_parent": null, "via_solution_label": null, "depth": 0}]"""


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
        system_prompt=SYSTEM_PROMPT,
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
