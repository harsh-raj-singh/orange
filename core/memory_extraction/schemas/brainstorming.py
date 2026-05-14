from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class BrainstormOption(BaseModel):
    option: str
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)
    discussed_in_messages: List[int] = Field(default_factory=list)


class BrainstormDecision(BaseModel):
    chosen: str = ""
    reasoning: str = ""
    tradeoffs_accepted: List[str] = Field(default_factory=list)
    recommendation: str = ""


class BrainstormingPayload(BaseModel):
    type: str = "brainstorming"
    topic: str = ""
    options_explored: List[BrainstormOption] = Field(default_factory=list)
    decision: BrainstormDecision = Field(default_factory=BrainstormDecision)
