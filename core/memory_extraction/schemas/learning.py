from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class LearningPayload(BaseModel):
    type: str = "learning"
    topic: str = ""
    project_context: str = ""
    key_takeaways: List[str] = Field(default_factory=list)
    aha_moments: List[str] = Field(default_factory=list)
