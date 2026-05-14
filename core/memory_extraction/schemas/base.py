from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ConversationType = Literal["debugging", "brainstorming", "code_review", "learning", "casual", "fallback", "legacy"]


class ConversationMetadata(BaseModel):
    type: ConversationType
    turns: int = 0
    duration_minutes: int = 0
    marked_complete_by_user: bool = True
    success_outcome: bool = False
    extraction_depth: str = "medium"


class Concept(BaseModel):
    name: str
    type: str
    level: int = 1
    context: str = ""


class Relationship(BaseModel):
    source: str
    relation: str
    target: str


class SearchableSummary(BaseModel):
    query_intent: str = ""
    solution_summary: str = ""
    keywords: List[str] = Field(default_factory=list)


class ExtractedMemory(BaseModel):
    chat_id: str
    user_id: str
    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    conversation_metadata: ConversationMetadata
    memory_payload: Dict[str, Any] = Field(default_factory=dict)
    extracted_concepts: List[Concept] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    searchable_summary: SearchableSummary = Field(default_factory=SearchableSummary)
    importance_score: float = 0.5
    extraction_confidence: float = 0.5
    extraction_version: str = "dspy_v1"
    processing_state: Literal["processed", "skipped", "failed"] = "processed"
    skip_reason: Optional[str] = None


class SkipResult(BaseModel):
    processing_state: Literal["skipped"] = "skipped"
    reason: str
    importance_score: float = 0.0
    extraction_confidence: float = 1.0


class FallbackResult(BaseModel):
    processing_state: Literal["processed"] = "processed"
    type: Literal["fallback"] = "fallback"
    error: str
