from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class PingContextRequest:
    query: str
    user_id: str
    source: str
    min_score: float = 0.70


@dataclass
class MatchedNode:
    node_type: str
    similarity_score: float
    node_data: dict
    neighborhood: dict


@dataclass
class PingContextResponse:
    query: str
    matched_nodes: list[MatchedNode]
    node_ids_used: list[str]


@dataclass
class StoreSessionRequest:
    transcript: str = ""
    source: str = ""
    user_id: str = ""
    session_id: str = ""
    external_session_id: str | None = None
    org_id: str | None = None
    started_at: datetime | str | int | float | None = None
    ended_at: datetime | str | int | float | None = None
    participants: list[str | dict[str, Any]] = field(default_factory=list)
    client_name: str | None = None
    client_version: str | None = None
    source_url: str | None = None
    client_metadata: dict[str, Any] = field(default_factory=dict)
    tool_metadata: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StoreSessionResponse:
    session_id: str
    problems_created: int
    problems_merged: int
    solutions_written: int
    errors: list[str] = field(default_factory=list)


@dataclass
class ResolveProblemRequest:
    session_id: str
    user_id: str
    problem_label: str
    solution_that_worked: str


@dataclass
class ResolveProblemResponse:
    resolved: bool
    problem_node_id: str | None
    solution_node_id: str | None
