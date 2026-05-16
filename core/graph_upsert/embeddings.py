from __future__ import annotations

from core.graph_schema_v2 import Concept, Insight, Problem, Solution


def build_problem_embed_string(problem: Problem) -> str:
    """Use canonical label plus contextual clause to avoid short-label collisions."""

    return f"{problem.canonical_label} - {problem.description}".strip()


def build_solution_embed_string(solution: Solution) -> str:
    """Use short label plus actionable text for higher semantic fidelity."""

    return f"{solution.canonical_label}: {solution.description}".strip()


def build_concept_embed_string(concept: Concept) -> str:
    """Concept labels are coarse-grained enough to embed directly."""

    return concept.canonical_label


def build_insight_embed_string(insight: Insight) -> str:
    """Embed the full technical learning, not just the display copy."""

    parts = [
        insight.what,
        insight.why or "",
        insight.how or "",
        insight.memory_kind,
        " ".join(insight.tags),
    ]
    return " ".join(part.strip() for part in parts if part and part.strip()).strip()
