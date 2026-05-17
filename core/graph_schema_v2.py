"""Graph schema v2 contracts for node models, edge types, normalization, and validation.

This module is intentionally self-contained so downstream extractors, mergers,
and upsert pipelines can import a single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_node_id() -> str:
    return f"node_{uuid4().hex}"


class NodeType(str, Enum):
    SESSION = "session"
    INSIGHT = "insight"
    PROBLEM = "problem"
    SOLUTION = "solution"
    CONCEPT = "concept"
    ARTIFACT = "artifact"


class SourceType(str, Enum):
    MCP = "mcp"
    CODEX = "codex"
    CURSOR = "cursor"
    CLAUDE = "claude"
    SLACK = "slack"
    GMAIL = "gmail"
    STREAMLIT = "streamlit"


class ConversationType(str, Enum):
    DEBUGGING = "debugging"
    CODE_REVIEW = "code_review"
    BRAINSTORMING = "brainstorming"
    PLANNING = "planning"
    LEARNING = "learning"
    DECISION_MAKING = "decision_making"
    GENERAL = "general"


class SessionResolutionStatus(str, Enum):
    OPEN = "open"
    PARTIALLY_RESOLVED = "partially_resolved"
    RESOLVED = "resolved"


class ProblemSeverity(str, Enum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProblemStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    RECURRED = "recurred"


class ConceptCategory(str, Enum):
    FRAMEWORK = "framework"
    PROTOCOL = "protocol"
    LIBRARY = "library"
    TOOL = "tool"
    LANGUAGE = "language"
    PLATFORM = "platform"
    INFRASTRUCTURE = "infrastructure"
    PATTERN = "pattern"
    DOMAIN = "domain"
    OTHER = "other"


class DecisionStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class ArtifactType(str, Enum):
    CODE_SNIPPET = "code_snippet"
    CONFIG = "config"
    COMMAND = "command"
    LOG = "log"
    QUERY = "query"
    DOCUMENTATION = "documentation"
    LINK = "link"
    TEST_CASE = "test_case"
    OTHER = "other"


class ConfidenceLevel(str, Enum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SolutionOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"  # fixed part of the problem
    FAILED = "failed"  # tried, did not work
    UNTRIED = "untried"  # suggested but not applied
    CAUSED_NEW_PROBLEM = "caused_new_problem"  # attempt introduced a new error


class InsightOutcome(str, Enum):
    RESOLVED = "resolved"
    EXPLORATORY = "exploratory"
    PARTIAL = "partial"
    ABANDONED = "abandoned"


class NodeBase(BaseModel):
    """Shared identity and provenance fields for all graph nodes."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(
        default_factory=_new_node_id,
        description="Stable unique identifier for this node instance in the graph.",
    )
    source: SourceType = Field(
        default=SourceType.STREAMLIT,
        description="Origin channel for this node. Use enum values only for consistency.",
    )
    created_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp when this node was first created.",
    )
    updated_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp of the last mutation applied to this node.",
    )
    extraction_version: str = Field(
        default="v2",
        description="Extractor/schema version that produced this node payload.",
    )


class Session(NodeBase):
    """Conversation-level node that tracks lifecycle and resolution at session scope."""

    node_type: Literal[NodeType.SESSION] = Field(
        default=NodeType.SESSION,
        description="Fixed discriminator for session nodes.",
    )
    conversation_type: ConversationType = Field(
        default=ConversationType.GENERAL,
        description="Primary interaction mode for the session.",
    )
    resolution_status: SessionResolutionStatus = Field(
        default=SessionResolutionStatus.OPEN,
        description=(
            "Session-level outcome status. This describes the whole session and can remain "
            "'open' even when one solution is known to work (for example when recurrence "
            "or unresolved sibling issues still exist)."
        ),
    )
    title: str = Field(
        default="",
        description="Short human-readable title for quick inspection in tooling.",
    )
    summary: str = Field(
        default="",
        description="Brief narrative summary of what happened in this session.",
    )
    started_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp when the session started.",
    )
    ended_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the session ended. None means still active or unknown.",
    )
    message_count: int = Field(
        default=0,
        ge=0,
        description="Count of messages observed in the session transcript.",
    )
    external_session_id: str | None = Field(
        default=None,
        description="Original session/thread/conversation id from the source system.",
    )
    org_id: str | None = Field(
        default=None,
        description="Tenant or organization id when available.",
    )
    participants: list[str] = Field(
        default_factory=list,
        description="Stable participant ids or names observed in the source session.",
    )
    client_name: str | None = Field(
        default=None,
        description="Calling client or agentic system name, e.g. claude-code or cursor.",
    )
    client_version: str | None = Field(
        default=None,
        description="Optional calling client version.",
    )
    source_url: str | None = Field(
        default=None,
        description="Optional URL or locator for the original source session.",
    )
    ingested_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp when Orange ingested the session.",
    )

    @field_validator("ended_at")
    @classmethod
    def _validate_end_time(cls, value: datetime | None) -> datetime | None:
        return value


class Problem(NodeBase):
    node_type: Literal[NodeType.PROBLEM] = Field(
        default=NodeType.PROBLEM,
    )

    # Core identity
    canonical_label: str = Field(
        default="",
        description="Short precise label e.g. 'TS2344 generic constraint mismatch in UserService'",
    )
    description: str = Field(
        default="",
        description="Full description of the error as observed",
    )
    llm_reasoning: str = Field(
        default="",
        description="Why the extraction agent identified this as a distinct problem",
    )

    # Technical context — capture everything extractable
    error_code: str | None = Field(
        default=None,
        description="e.g. 'TS2344', 'ECONNREFUSED', 'ModuleNotFoundError'",
    )
    error_type: str | None = Field(
        default=None,
        description="e.g. 'TypeError', 'SyntaxError', 'RuntimeError'",
    )
    stack_trace_summary: str | None = Field(
        default=None,
        description="First 2-3 lines of stack trace if present",
    )
    affected_file_paths: list[str] = Field(
        default_factory=list,
    )
    relevant_code: list[str] = Field(
        default_factory=list,
        description="Key code snippets directly involved in this problem",
    )
    tech_stack: list[str] = Field(
        default_factory=list,
        description="e.g. ['Python 3.11', 'FastAPI', 'PostgreSQL']",
    )
    # Prior context chain — denormalized at write time for self-contained retrieval
    prior_solution_contexts: list[str] = Field(
        default_factory=list,
        description="Ordered list of solution summaries that were attempted before this problem appeared. Full chain, oldest first.",
    )

    # Hierarchy
    parent_problem_label: str | None = Field(
        default=None,
        description="canonical_label of parent — resolved to ID at write time",
    )
    depth: int = Field(
        default=0,
        ge=0,
    )
    root_cause_known: bool = Field(
        default=False,
    )
    root_cause_description: str | None = Field(
        default=None,
    )

    # Turn tracking
    turn_sequence: list[int] = Field(
        default_factory=list,
        description="All turn numbers where this problem appears",
    )
    first_seen_turn: int | None = Field(
        default=None,
        ge=1,
    )
    last_seen_turn: int | None = Field(
        default=None,
        ge=1,
    )


class Solution(NodeBase):
    node_type: Literal[NodeType.SOLUTION] = Field(
        default=NodeType.SOLUTION,
    )

    # Identity
    canonical_label: str = Field(
        default="",
    )
    description: str = Field(
        default="",
        description="What the solution does / what was attempted",
    )
    in_depth_summary: str = Field(
        default="",
        description="Complete detailed summary — this gets stuffed into the next problem node's prior_solution_contexts",
    )

    # Attempt detail
    outcome: SolutionOutcome = Field(
        default=SolutionOutcome.UNTRIED,
    )
    failure_reason: str | None = Field(
        default=None,
        description="Why it failed, if outcome=FAILED",
    )
    failure_error_code: str | None = Field(
        default=None,
        description="New error introduced, if any",
    )
    partial_fix_description: str | None = Field(
        default=None,
        description="What it did fix, if outcome=PARTIAL",
    )

    # What was actually done
    steps: list[str] = Field(
        default_factory=list,
        description="Concrete steps taken or proposed",
    )
    code_snippets: list[str] = Field(
        default_factory=list,
        description="Key code changes if mentioned",
    )
    tools_used: list[str] = Field(
        default_factory=list,
        description="e.g. ['pip', 'docker', 'git rebase']",
    )

    # Hierarchy — attempt ordering
    attempt_number: int = Field(
        default=1,
        ge=1,
        description="1 = first attempt at solving parent problem",
    )
    parent_solution_label: str | None = Field(
        default=None,
    )
    addresses_problem_label: str = Field(
        default="",
    )

    # Turn tracking
    applied_turn: int | None = Field(
        default=None,
        ge=1,
    )
    turn_sequence: list[int] = Field(
        default_factory=list,
    )
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.UNKNOWN,
    )


class Insight(NodeBase):
    """Unified durable memory node produced at completed-session scope."""

    node_type: Literal[NodeType.INSIGHT] = Field(
        default=NodeType.INSIGHT,
        description="Fixed discriminator for insight nodes.",
    )
    scope: Literal["user", "global"] = Field(
        default="user",
        description="Private user memory or shared sanitized global knowledge.",
    )
    user_id: str | None = Field(
        default=None,
        description="Email identity for user-scoped insights. Null for global insights.",
    )
    user_email: str | None = Field(
        default=None,
        description="Human-readable owner email for user-scoped lookup.",
    )
    org_id: str | None = Field(
        default=None,
        description="Company/org identity for shared company-scoped insights.",
    )
    company: str | None = Field(
        default=None,
        description="Display company name when supplied by the source profile.",
    )
    contributed_by: str | None = Field(
        default=None,
        description="Audit-only contributor email for global insights. Never exposed in shared retrieval.",
    )
    memory_kind: str = Field(
        default="technical_insight",
        description="technical_insight, user_fact, company_fact, preference, or steering.",
    )
    what: str = Field(
        default="",
        description="Situation, question, or problem captured by the insight.",
    )
    why: str | None = Field(
        default=None,
        description="Root cause or reason, if discovered.",
    )
    how: str | None = Field(
        default=None,
        description="What was tried, done, or resolved.",
    )
    outcome: InsightOutcome = Field(
        default=InsightOutcome.EXPLORATORY,
        description="Outcome classification for graph display and retrieval.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Specific technical/domain tags used for retrieval.",
    )
    display_label: str = Field(
        default="",
        description="Compact graph card label.",
    )
    display_summary: str = Field(
        default="",
        description="Compact graph card summary.",
    )
    raw_session_id: str = Field(
        default="",
        description="Session node id that produced this insight.",
    )


class Concept(NodeBase):
    """Knowledge node for reusable technologies, domains, protocols, and abstractions."""

    node_type: Literal[NodeType.CONCEPT] = Field(
        default=NodeType.CONCEPT,
        description="Fixed discriminator for concept nodes.",
    )
    canonical_label: str = Field(
        default="",
        description="Normalized concept label used for identity and matching.",
    )
    category: ConceptCategory = Field(
        default=ConceptCategory.OTHER,
        description="Controlled category to avoid freeform taxonomy drift.",
    )
    description: str = Field(
        default="",
        description="Short explanatory context for the concept.",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative surface forms that map to the same concept.",
    )


class Artifact(NodeBase):
    """Concrete output node such as commands, snippets, configs, logs, or docs."""

    node_type: Literal[NodeType.ARTIFACT] = Field(
        default=NodeType.ARTIFACT,
        description="Fixed discriminator for artifact nodes.",
    )
    canonical_label: str = Field(
        default="",
        description="Normalized short label describing the artifact.",
    )
    artifact_type: ArtifactType = Field(
        default=ArtifactType.OTHER,
        description="Controlled artifact class used for downstream tooling behavior.",
    )
    locator: str = Field(
        default="",
        description="Pointer to artifact location (path, URL, or synthetic key).",
    )
    language: str | None = Field(
        default=None,
        description="Optional language/runtime context (python, sql, bash, etc.).",
    )
    content_hash: str | None = Field(
        default=None,
        description="Optional deterministic hash for dedupe and integrity checks.",
    )
    summary: str = Field(
        default="",
        description="Short human-readable summary of artifact content.",
    )

class EdgeType(str, Enum):
    # existing
    BELONGS_TO = "BELONGS_TO"
    HAS_PROBLEM = "HAS_PROBLEM"
    PROPOSED_FOR = "PROPOSED_FOR"
    RESOLVED_BY = "RESOLVED_BY"
    RECURS_AS = "RECURS_AS"
    TRIED_IN = "TRIED_IN"
    RELATED_TO = "RELATED_TO"
    SIMILAR_TO = "SIMILAR_TO"
    PRODUCED = "PRODUCED"

    # new
    CAUSED_BY = "CAUSED_BY"  # Problem → Problem (child caused by parent's attempted fix)
    TRIGGERED_BY = "TRIGGERED_BY"  # Problem → Problem (sub-problem triggered during parent debugging)
    ATTEMPTED_BY = "ATTEMPTED_BY"  # Problem → Solution (attempt, carries outcome)
    REFINED_BY = "REFINED_BY"  # Solution → Solution (second attempt refined from first)
    PRECEDED_BY = "PRECEDED_BY"  # Problem → Problem (ordering, not causal)


@dataclass(frozen=True)
class BelongsToEdge:
    """Hierarchy edge.

    Valid directions:
    - Problem -> Concept: attach a concrete problem under a broader concept.
    - Concept -> Concept: build concept trees (for example cors -> fastapi).

    This supports sibling retrieval by walking up to parent concept and then down
    to neighboring problems/concepts.
    """

    from_node_type: Literal[NodeType.PROBLEM, NodeType.CONCEPT]
    to_node_type: Literal[NodeType.CONCEPT] = NodeType.CONCEPT
    edge_type: Literal[EdgeType.BELONGS_TO] = EdgeType.BELONGS_TO


@dataclass(frozen=True)
class HasProblemEdge:
    """Session -> Problem membership edge."""

    from_node_type: Literal[NodeType.SESSION] = NodeType.SESSION
    to_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    edge_type: Literal[EdgeType.HAS_PROBLEM] = EdgeType.HAS_PROBLEM


@dataclass(frozen=True)
class ProposedForEdge:
    """Solution -> Problem proposal edge."""

    from_node_type: Literal[NodeType.SOLUTION] = NodeType.SOLUTION
    to_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    edge_type: Literal[EdgeType.PROPOSED_FOR] = EdgeType.PROPOSED_FOR


@dataclass(frozen=True)
class ResolvedByEdge:
    """Problem -> Solution confirmed resolution edge."""

    from_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    to_node_type: Literal[NodeType.SOLUTION] = NodeType.SOLUTION
    edge_type: Literal[EdgeType.RESOLVED_BY] = EdgeType.RESOLVED_BY


@dataclass(frozen=True)
class RecursAsEdge:
    """Session -> Problem recurrence edge with explicit recurrence ordering."""

    from_node_type: Literal[NodeType.SESSION] = NodeType.SESSION
    to_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    recurrence_index: int = 1
    edge_type: Literal[EdgeType.RECURS_AS] = EdgeType.RECURS_AS


@dataclass(frozen=True)
class TriedInEdge:
    """Solution -> Session edge representing that a solution was tried in a session."""

    from_node_type: Literal[NodeType.SOLUTION] = NodeType.SOLUTION
    to_node_type: Literal[NodeType.SESSION] = NodeType.SESSION
    edge_type: Literal[EdgeType.TRIED_IN] = EdgeType.TRIED_IN


@dataclass(frozen=True)
class RelatedToEdge:
    """Problem -> Problem edge for lateral similarity/association links."""

    from_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    to_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    edge_type: Literal[EdgeType.RELATED_TO] = EdgeType.RELATED_TO


@dataclass(frozen=True)
class SimilarToEdge:
    """Problem -> Problem semantic similarity link."""

    from_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    to_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    edge_type: Literal[EdgeType.SIMILAR_TO] = EdgeType.SIMILAR_TO
    similarity_score: float | None = None


@dataclass(frozen=True)
class CausedByEdge:
    """Child problem caused by a solution attempt on parent problem."""

    from_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    to_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    edge_type: Literal[EdgeType.CAUSED_BY] = EdgeType.CAUSED_BY
    via_solution_label: str | None = None


@dataclass(frozen=True)
class TriggeredByEdge:
    """Sub-problem discovered while debugging parent — not necessarily caused by a fix."""

    from_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    to_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    edge_type: Literal[EdgeType.TRIGGERED_BY] = EdgeType.TRIGGERED_BY


@dataclass(frozen=True)
class AttemptedByEdge:
    """Problem was addressed by this solution. Outcome lives on Solution node."""

    from_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    to_node_type: Literal[NodeType.SOLUTION] = NodeType.SOLUTION
    edge_type: Literal[EdgeType.ATTEMPTED_BY] = EdgeType.ATTEMPTED_BY
    attempt_number: int = 1


@dataclass(frozen=True)
class RefinedByEdge:
    """Solution B is a refinement/follow-up of Solution A."""

    from_node_type: Literal[NodeType.SOLUTION] = NodeType.SOLUTION
    to_node_type: Literal[NodeType.SOLUTION] = NodeType.SOLUTION
    edge_type: Literal[EdgeType.REFINED_BY] = EdgeType.REFINED_BY


@dataclass(frozen=True)
class PrecededByEdge:
    """Problem B came after Problem A in the session (ordering, not causal)."""

    from_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    to_node_type: Literal[NodeType.PROBLEM] = NodeType.PROBLEM
    edge_type: Literal[EdgeType.PRECEDED_BY] = EdgeType.PRECEDED_BY


EdgeModel = Union[
    BelongsToEdge,
    HasProblemEdge,
    ProposedForEdge,
    ResolvedByEdge,
    RecursAsEdge,
    TriedInEdge,
    RelatedToEdge,
    SimilarToEdge,
    CausedByEdge,
    TriggeredByEdge,
    AttemptedByEdge,
    RefinedByEdge,
    PrecededByEdge,
]


_NODE_TYPE_BY_MODEL = {
    Session: NodeType.SESSION,
    Insight: NodeType.INSIGHT,
    Problem: NodeType.PROBLEM,
    Solution: NodeType.SOLUTION,
    Concept: NodeType.CONCEPT,
    Artifact: NodeType.ARTIFACT,
}

_ALLOWED_EDGE_DIRECTIONS: dict[EdgeType, set[tuple[NodeType, NodeType]]] = {
    EdgeType.BELONGS_TO: {
        (NodeType.PROBLEM, NodeType.CONCEPT),
        (NodeType.CONCEPT, NodeType.CONCEPT),
    },
    EdgeType.HAS_PROBLEM: {
        (NodeType.SESSION, NodeType.PROBLEM),
    },
    EdgeType.PROPOSED_FOR: {
        (NodeType.SOLUTION, NodeType.PROBLEM),
    },
    EdgeType.RESOLVED_BY: {
        (NodeType.PROBLEM, NodeType.SOLUTION),
    },
    EdgeType.RECURS_AS: {
        (NodeType.SESSION, NodeType.PROBLEM),
    },
    EdgeType.TRIED_IN: {
        (NodeType.SOLUTION, NodeType.SESSION),
    },
    EdgeType.RELATED_TO: {
        (NodeType.PROBLEM, NodeType.PROBLEM),
    },
    EdgeType.SIMILAR_TO: {
        (NodeType.PROBLEM, NodeType.PROBLEM),
        (NodeType.INSIGHT, NodeType.INSIGHT),
    },
    EdgeType.PRODUCED: {
        (NodeType.SESSION, NodeType.INSIGHT),
    },
    EdgeType.CAUSED_BY: {
        (NodeType.PROBLEM, NodeType.PROBLEM),
    },
    EdgeType.TRIGGERED_BY: {
        (NodeType.PROBLEM, NodeType.PROBLEM),
    },
    EdgeType.ATTEMPTED_BY: {
        (NodeType.PROBLEM, NodeType.SOLUTION),
    },
    EdgeType.REFINED_BY: {
        (NodeType.SOLUTION, NodeType.SOLUTION),
    },
    EdgeType.PRECEDED_BY: {
        (NodeType.PROBLEM, NodeType.PROBLEM),
    },
}


def _node_type_for_instance(node: BaseModel) -> NodeType:
    for model_cls, node_type in _NODE_TYPE_BY_MODEL.items():
        if isinstance(node, model_cls):
            return node_type
    raise ValueError(
        "Unsupported node model. Expected one of: Session, Insight, Problem, Solution, Concept, Artifact."
    )


def validate_node(node: BaseModel) -> None:
    """Validate a node payload before graph/vector persistence."""

    if not isinstance(node, BaseModel):
        raise ValueError("validate_node expected a Pydantic BaseModel instance.")

    node_type = _node_type_for_instance(node)

    if hasattr(node, "canonical_label"):
        label = getattr(node, "canonical_label")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{node_type.value}.canonical_label is required and must be non-empty.")

    if isinstance(node, Insight):
        if not node.what.strip():
            raise ValueError("Insight.what is required and must be non-empty.")
        if not node.display_label.strip():
            raise ValueError("Insight.display_label is required and must be non-empty.")

    if isinstance(node, Session):
        if node.ended_at is not None and node.ended_at < node.started_at:
            raise ValueError("Session.ended_at must be >= Session.started_at.")

def validate_edge(edge: EdgeModel, source_node: BaseModel, target_node: BaseModel) -> None:
    """Validate edge type and direction against the strict From->To table."""

    if not isinstance(
        edge,
        (
            BelongsToEdge,
            HasProblemEdge,
            ProposedForEdge,
            ResolvedByEdge,
            RecursAsEdge,
            TriedInEdge,
            RelatedToEdge,
            SimilarToEdge,
            CausedByEdge,
            TriggeredByEdge,
            AttemptedByEdge,
            RefinedByEdge,
            PrecededByEdge,
        ),
    ):
        raise ValueError("Unsupported edge model passed to validate_edge.")

    source_type = _node_type_for_instance(source_node)
    target_type = _node_type_for_instance(target_node)

    if edge.from_node_type != source_type:
        raise ValueError(
            f"Edge source mismatch: edge expects {edge.from_node_type.value}, got {source_type.value}."
        )
    if edge.to_node_type != target_type:
        raise ValueError(
            f"Edge target mismatch: edge expects {edge.to_node_type.value}, got {target_type.value}."
        )

    allowed_pairs = _ALLOWED_EDGE_DIRECTIONS.get(edge.edge_type, set())
    if (source_type, target_type) not in allowed_pairs:
        raise ValueError(
            f"Invalid edge direction for {edge.edge_type.value}: {source_type.value} -> {target_type.value}."
        )

    if isinstance(edge, RecursAsEdge) and edge.recurrence_index < 1:
        raise ValueError("RecursAsEdge.recurrence_index must be >= 1.")
    if isinstance(edge, AttemptedByEdge) and edge.attempt_number < 1:
        raise ValueError("AttemptedByEdge.attempt_number must be >= 1.")
