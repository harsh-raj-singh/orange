"""Data contracts between the active extraction agents and the writer."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator


class TriageDecision(BaseModel):
    should_store: bool = Field(validation_alias=AliasChoices("should_store", "worth_storing"))
    suggested_scope: Literal["user", "global", "both"] = "user"
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    low_confidence: bool = False
    reason: str

    @model_validator(mode="after")
    def flag_low_confidence(self) -> "TriageDecision":
        self.low_confidence = self.low_confidence or self.confidence < 0.6
        return self

    @property
    def worth_storing(self) -> bool:
        return self.should_store


class InsightDraft(BaseModel):
    what: str
    why: str | None = None
    how: str | None = None
    outcome: str = "exploratory"
    memory_kind: str = "technical_insight"
    tags: list[str] = Field(default_factory=list)
    display_label: str
    display_summary: str
