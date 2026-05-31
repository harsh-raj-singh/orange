"""Active graph contracts for Orange.

The runtime graph has one durable memory node shape: ``Insight``. A completed
session can produce private user insights and sanitized company-scoped global
insights. Older Problem/Solution models lived here during rollout; they are
retired from the active write path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_node_id() -> str:
    return f"node_{uuid4().hex}"


class NodeType(str, Enum):
    SESSION = "session"
    INSIGHT = "insight"


class SourceType(str, Enum):
    MCP = "mcp"
    CODEX = "codex"
    CURSOR = "cursor"
    CLAUDE = "claude"
    SLACK = "slack"
    GMAIL = "gmail"


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


class InsightOutcome(str, Enum):
    RESOLVED = "resolved"
    EXPLORATORY = "exploratory"
    PARTIAL = "partial"
    ABANDONED = "abandoned"


class NodeBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(default_factory=_new_node_id)
    source: SourceType = SourceType.CURSOR
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    extraction_version: str = "v2"


class Session(NodeBase):
    node_type: Literal[NodeType.SESSION] = NodeType.SESSION
    conversation_type: ConversationType = ConversationType.GENERAL
    resolution_status: SessionResolutionStatus = SessionResolutionStatus.OPEN
    title: str = ""
    summary: str = ""
    started_at: datetime = Field(default_factory=_utc_now)
    ended_at: datetime | None = None
    message_count: int = Field(default=0, ge=0)
    external_session_id: str | None = None
    org_id: str | None = None
    participants: list[str] = Field(default_factory=list)
    client_name: str | None = None
    client_version: str | None = None
    source_url: str | None = None
    ingested_at: datetime = Field(default_factory=_utc_now)


class Insight(NodeBase):
    node_type: Literal[NodeType.INSIGHT] = NodeType.INSIGHT
    scope: Literal["user", "global"] = "user"
    user_id: str | None = None
    user_email: str | None = None
    org_id: str | None = None
    company: str | None = None
    contributed_by: str | None = None
    memory_kind: str = "technical_insight"
    what: str
    why: str | None = None
    how: str | None = None
    outcome: InsightOutcome = InsightOutcome.EXPLORATORY
    tags: list[str] = Field(default_factory=list)
    display_label: str
    display_summary: str = ""
    raw_session_id: str = ""

    @field_validator("what", "display_label")
    @classmethod
    def _required_text(cls, value: str) -> str:
        cleaned = " ".join((value or "").split())
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned

    @field_validator("memory_kind")
    @classmethod
    def _clean_memory_kind(cls, value: str) -> str:
        cleaned = (value or "technical_insight").strip()
        return cleaned or "technical_insight"

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, values: list[str]) -> list[str]:
        return [str(value).strip() for value in values if str(value).strip()]


def validate_node(node: BaseModel) -> None:
    """Validate an active graph node before graph/vector persistence."""

    if not isinstance(node, BaseModel):
        raise ValueError("validate_node expected a Pydantic BaseModel instance.")
    if isinstance(node, Session):
        if node.ended_at is not None and node.ended_at < node.started_at:
            raise ValueError("Session.ended_at must be >= Session.started_at.")
        return
    if isinstance(node, Insight):
        if node.scope == "global" and not node.org_id:
            raise ValueError("Global insights require org_id.")
        if node.scope == "user" and not (node.user_id or node.user_email):
            raise ValueError("User insights require user_id or user_email.")
        return
    raise ValueError("Unsupported node model. Expected Session or Insight.")
