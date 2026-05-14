from __future__ import annotations

from core.graph_schema_v2 import Concept, Problem, Solution


def build_problem_embed_string(problem: Problem) -> str:
    """Use canonical label plus contextual clause to avoid short-label collisions."""

    return f"{problem.canonical_label} - {problem.context_brief}".strip()


def build_solution_embed_string(solution: Solution) -> str:
    """Use short label plus actionable text for higher semantic fidelity."""

    return f"{solution.canonical_label}: {solution.description}".strip()


def build_concept_embed_string(concept: Concept) -> str:
    """Concept labels are coarse-grained enough to embed directly."""

    return concept.canonical_label
