from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PingContextRequest:
    query: str
    user_id: str
    source: str


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
    transcript: str
    source: str
    user_id: str
    session_id: str


@dataclass
class StoreSessionResponse:
    session_id: str
    problems_created: int
    problems_merged: int
    solutions_written: int


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
