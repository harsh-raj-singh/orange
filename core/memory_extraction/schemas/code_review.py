from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class CodeIssue(BaseModel):
    issue: str
    severity: str = "medium"
    location: str = ""
    explanation: str = ""


class CodeSuggestion(BaseModel):
    suggestion: str
    rationale: str = ""
    applied: bool = False
    outcome: str = ""


class CodeReviewPayload(BaseModel):
    type: str = "code_review"
    codebase_summary: str = ""
    issues_found: List[CodeIssue] = Field(default_factory=list)
    suggestions: List[CodeSuggestion] = Field(default_factory=list)
