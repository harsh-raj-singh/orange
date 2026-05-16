"""
Pure data contracts. No LLM logic, no graph logic.
These are the interfaces between agents and the writer.
"""

from pydantic import BaseModel, Field

from core.graph_schema_v2 import ConfidenceLevel, SolutionOutcome


class RawProblemSegment(BaseModel):
    """Output of ProblemSegmenterAgent — one identified problem, not yet enriched."""

    segment_id: str  # temporary ID for this pipeline run only
    raw_description: str  # what the segmenter found
    relevant_turns: list[int]  # turn numbers this problem spans
    source_text: str  # the actual transcript excerpt


class EnrichedProblem(BaseModel):
    """One fully enriched problem after all Wave 1 + Wave 2 sub-agents complete."""

    segment_id: str  # matches RawProblemSegment.segment_id
    canonical_label: str
    description: str
    display_label: str = ""
    display_summary: str = ""
    raw_description: str = ""
    llm_reasoning: str
    error_code: str | None = None
    error_type: str | None = None
    stack_trace_summary: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    affected_file_paths: list[str] = Field(default_factory=list)
    relevant_code: list[str] = Field(default_factory=list)
    root_cause_known: bool = False
    root_cause_description: str | None = None
    recurrence_count: int = 0
    turn_sequence: list[int] = Field(default_factory=list)
    first_seen_turn: int | None = None
    last_seen_turn: int | None = None
    # Set by RelationshipAgent
    parent_segment_id: str | None = None
    relationship_to_parent: str | None = None  # "CAUSED_BY" | "TRIGGERED_BY" | None
    via_solution_label: str | None = None
    depth: int = 0
    # Set by ContextStitchingAgent
    prior_solution_contexts: list[str] = Field(default_factory=list)


class ExtractedSolution(BaseModel):
    """One solution extracted by the Solution Agent."""

    canonical_label: str
    description: str
    display_label: str = ""
    display_summary: str = ""
    raw_description: str = ""
    in_depth_summary: str
    outcome: SolutionOutcome = SolutionOutcome.UNTRIED
    failure_reason: str | None = None
    failure_error_code: str | None = None
    partial_fix_description: str | None = None
    steps: list[str] = Field(default_factory=list)
    code_snippets: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    attempt_number: int = 1
    parent_solution_label: str | None = None
    addresses_problem_label: str = ""
    applied_turn: int | None = None
    turn_sequence: list[int] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN


class IssueAgentOutput(BaseModel):
    session_id: str
    problems: list[EnrichedProblem]  # ordered by first_seen_turn


class SolutionAgentOutput(BaseModel):
    session_id: str
    solutions: list[ExtractedSolution]  # ordered by applied_turn


class TriageDecision(BaseModel):
    worth_storing: bool
    reason: str


class InsightDraft(BaseModel):
    what: str
    why: str | None = None
    how: str | None = None
    outcome: str = "exploratory"
    tags: list[str] = Field(default_factory=list)
    display_label: str
    display_summary: str
