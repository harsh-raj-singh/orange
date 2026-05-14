from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ProblemContext(BaseModel):
    platform: Optional[str] = None
    service: Optional[str] = None
    region: Optional[str] = None
    environment: Optional[str] = None


class DebugProblem(BaseModel):
    description: str = ""
    exact_error: str = ""
    context: ProblemContext = Field(default_factory=ProblemContext)
    symptoms: List[str] = Field(default_factory=list)


class InvestigationStep(BaseModel):
    attempt: int
    action: str
    result: str
    outcome: str


class DebugSolution(BaseModel):
    root_cause: str = ""
    fix_applied: str = ""
    exact_steps: List[str] = Field(default_factory=list)
    verification: str = ""


class LLMMistake(BaseModel):
    what_llm_said: str
    user_response: str
    why_wrong: str


class DebuggingPayload(BaseModel):
    type: str = "debugging"
    problem: DebugProblem = Field(default_factory=DebugProblem)
    investigation_path: List[InvestigationStep] = Field(default_factory=list)
    solution: DebugSolution = Field(default_factory=DebugSolution)
    llm_mistakes: List[LLMMistake] = Field(default_factory=list)
    failed_solutions: List[dict] = Field(default_factory=list)
    key_learnings: List[str] = Field(default_factory=list)
