from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# Node types — LLM must pick from this list only
NODE_TYPES = [
    "session",        # one per chat, root node
    "problem",        # a specific issue, error, or question raised
    "attempt",        # something tried that may or may not have worked
    "solution",       # confirmed working fix or answer
    "concept",        # reusable idea, pattern, technology, term
    "context",        # environment info: stack, versions, constraints, participants
    "decision",       # a choice made and the reasoning behind it
    "open_question",  # unresolved question at end of chat
    "artifact",       # concrete output: code snippet, config, command, prompt
]

# Relationship types — LLM must pick from this list only
RELATIONSHIP_TYPES = [
    "HAS_PROBLEM",        # session -> problem
    "HAS_CONTEXT",        # session or problem -> context
    "ATTEMPTED",          # problem -> attempt
    "FAILED_BECAUSE",     # attempt -> problem/concept (why it didn't work)
    "SOLVED_BY",          # problem -> solution
    "PARTIAL_FIX",        # attempt -> problem (helped but didn't fully solve)
    "RELATED_TO",         # lateral, any node -> any node, same level
    "DEPENDS_ON",         # concept/solution -> concept/tool
    "LED_TO",             # attempt or decision -> next problem or concept
    "CONTRADICTS",        # concept or attempt -> another concept or attempt
    "REFERENCES",         # any node -> artifact
    "RAISED_IN",          # open_question -> session
    "PART_OF",            # detail node -> parent node
]

# Session intent types — LLM classifies one per session
SESSION_INTENTS = [
    "debugging",
    "code_review",
    "brainstorming",
    "planning",
    "learning",
    "decision_making",
    "general",
]

# Hierarchy levels
LEVEL_SESSION = 1     # session node
LEVEL_PRIMARY = 2     # problem, decision, open_question
LEVEL_SECONDARY = 3   # attempt, solution, context
LEVEL_DETAIL = 4      # artifact, concept, granular facts

SOURCE_TYPES = {"chat", "mcp", "slack", "gmail"}
OUTCOME_VALUES = {"worked", "failed", "partial", "unknown"}


class GraphNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))  # uuid
    name: str = Field(default="", max_length=100)          # short label, max 100 chars
    display_name: str = Field(default="", max_length=80)   # 2-4 word visualization label
    node_type: str                                          # from NODE_TYPES
    level: int                                              # from LEVEL_ constants
    context: str = ""                                       # 1-2 sentence description
    session_intent: str                                     # from SESSION_INTENTS, inherited from parent session
    source_type: str = "chat"                              # "chat" | "mcp" | "slack" | "gmail"
    chat_ids: List[str] = Field(default_factory=list)      # which chats mentioned this node
    vector_refs: List[str] = Field(default_factory=list)   # chroma vector IDs pointing to this node
    user_ids: List[str] = Field(default_factory=list)      # which users contributed (anonymized at retrieval)
    embedding: Optional[List[float]] = None
    mention_count: int = 1                                  # incremented on each reuse
    importance: float = 0.5                                 # 0.0 - 1.0
    outcome: Optional[str] = "unknown"                      # worked|failed|partial|unknown
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extraction_version: str = "dspy_v1"

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("name must not be empty")
        if len(cleaned) > 100:
            return cleaned[:100]
        return cleaned

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str) -> str:
        cleaned = " ".join((value or "").strip().split())
        if len(cleaned) > 80:
            return cleaned[:80]
        return cleaned

    @field_validator("node_type")
    @classmethod
    def _validate_node_type(cls, value: str) -> str:
        if value not in NODE_TYPES:
            raise ValueError(f"node_type must be one of {NODE_TYPES}")
        return value

    @field_validator("level")
    @classmethod
    def _validate_level(cls, value: int) -> int:
        if value not in {LEVEL_SESSION, LEVEL_PRIMARY, LEVEL_SECONDARY, LEVEL_DETAIL}:
            raise ValueError("level must be one of 1, 2, 3, 4")
        return value

    @field_validator("session_intent")
    @classmethod
    def _validate_session_intent(cls, value: str) -> str:
        if value not in SESSION_INTENTS:
            raise ValueError(f"session_intent must be one of {SESSION_INTENTS}")
        return value

    @field_validator("source_type")
    @classmethod
    def _validate_source_type(cls, value: str) -> str:
        if value not in SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {sorted(SOURCE_TYPES)}")
        return value

    @field_validator("mention_count")
    @classmethod
    def _validate_mention_count(cls, value: int) -> int:
        return max(1, int(value))

    @field_validator("importance")
    @classmethod
    def _validate_importance(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @field_validator("outcome")
    @classmethod
    def _validate_outcome(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value not in OUTCOME_VALUES:
            return "unknown"
        return value

    @model_validator(mode="after")
    def _ensure_display_name(self) -> "GraphNode":
        if not self.display_name:
            self.display_name = " ".join(self.name.split()[:4]).title()[:80]
        return self
