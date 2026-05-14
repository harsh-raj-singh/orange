from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pytest


@dataclass
class FakeResult:
    record: dict[str, Any] | None = None

    def single(self) -> dict[str, Any] | None:
        return self.record


class FakeNeo4j:
    def __init__(self) -> None:
        self.sessions: dict[tuple[str, str], dict[str, Any]] = {}
        self.concepts: dict[tuple[str, str], dict[str, Any]] = {}
        self.problems: dict[tuple[str, str], dict[str, Any]] = {}
        self.solutions: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.edges: set[tuple[str, str, str, str]] = set()
        self.query_log: list[tuple[str, dict[str, Any]]] = []
        self.problem_create_calls = 0

    def run(self, query: str, **params: Any) -> FakeResult:
        self.query_log.append((query, params))

        if "H4:CHECK_CONTENT_HASH_PROBLEM" in query:
            for (node_id, uid), payload in self.problems.items():
                if uid == params["user_id"] and payload.get("content_hash") == params["content_hash"]:
                    return FakeResult({"node_id": node_id})
            return FakeResult(None)

        if "H4:CHECK_CONTENT_HASH_SOLUTION" in query:
            for (_, _, uid), payload in self.solutions.items():
                if uid == params["user_id"] and payload.get("content_hash") == params["content_hash"]:
                    return FakeResult({"node_id": payload["node_id"]})
            return FakeResult(None)

        if "H4:MERGE_SESSION" in query:
            key = (params["node_id"], params["user_id"])
            self.sessions[key] = dict(params)
            return FakeResult({"node_id": params["node_id"]})

        if "H4:MERGE_CONCEPT" in query:
            key = (params["canonical_label"], params["user_id"])
            existing = self.concepts.get(key, {})
            node_id = existing.get("node_id", params["node_id"])
            payload = dict(params)
            payload["node_id"] = node_id
            self.concepts[key] = payload
            return FakeResult({"node_id": node_id})

        if "H4:CREATE_PROBLEM" in query:
            self.problem_create_calls += 1
            key = (params["node_id"], params["user_id"])
            payload = dict(params)
            self.problems[key] = payload
            return FakeResult({"node_id": params["node_id"]})

        if "H4:INCREMENT_RECURRENCE" in query:
            key = (params["problem_id"], params["user_id"])
            payload = self.problems.get(key)
            if payload:
                payload["recurrence_count"] = int(payload.get("recurrence_count", 0)) + 1
            return FakeResult(None)

        if "H4:MERGE_SOLUTION" in query:
            key = (params["canonical_label"], params["parent_problem_id"], params["user_id"])
            existing = self.solutions.get(key, {})
            node_id = existing.get("node_id", params["node_id"])
            payload = dict(params)
            payload["node_id"] = node_id
            self.solutions[key] = payload
            return FakeResult({"node_id": node_id})

        marker_match = re.search(r"H4:EDGE_([A-Z_]+)", query)
        if marker_match:
            marker = marker_match.group(1)
            edge_type = {
                "CONCEPT_BELONGS_TO": "BELONGS_TO",
                "PROBLEM_BELONGS_TO": "BELONGS_TO",
                "HAS_PROBLEM": "HAS_PROBLEM",
                "RECURS_AS": "RECURS_AS",
                "PROPOSED_FOR": "PROPOSED_FOR",
                "CROSS_SESSION_PROPOSED_FOR": "PROPOSED_FOR",
                "RESOLVED_BY": "RESOLVED_BY",
                "RELATED_TO": "RELATED_TO",
            }[marker]
            src = (
                params.get("session_id")
                or params.get("child_id")
                or params.get("problem_id")
                or params.get("solution_id")
            )
            dst = params.get("problem_id") or params.get("parent_id") or params.get("concept_id") or params.get("solution_id")

            if marker == "PROPOSED_FOR":
                src = params.get("solution_id")
                dst = params.get("problem_id")
            if marker == "CROSS_SESSION_PROPOSED_FOR":
                src = params.get("solution_id")
                dst = params.get("problem_id")
            if marker == "RESOLVED_BY":
                src = params.get("problem_id")
                dst = params.get("solution_id")
            if marker == "HAS_PROBLEM":
                src = params.get("session_id")
                dst = params.get("problem_id")
            if marker == "RECURS_AS":
                src = params.get("session_id")
                dst = params.get("problem_id")
            if marker == "CONCEPT_BELONGS_TO":
                src = params.get("child_id")
                dst = params.get("parent_id")
            if marker == "PROBLEM_BELONGS_TO":
                src = params.get("problem_id")
                dst = params.get("concept_id")

            self.edges.add((edge_type, str(src), str(dst), params["user_id"]))
            return FakeResult(None)

        if "H6:FIND_PROBLEM_BY_LABEL" in query:
            label = params.get("label")
            user_id = params.get("user_id")
            for (node_id, uid), payload in self.problems.items():
                if uid == user_id and payload.get("canonical_label") == label:
                    return FakeResult(
                        {
                            "node_id": node_id,
                            "canonical_label": payload.get("canonical_label"),
                            "context_brief": payload.get("context_brief", ""),
                            "status": payload.get("status", "open"),
                        }
                    )
            return FakeResult(None)

        if "H6:UPSERT_RESOLVE_SOLUTION" in query:
            key = (params["canonical_label"], params["problem_id"], params["user_id"])
            existing = self.solutions.get(key, {})
            node_id = existing.get("node_id", params["node_id"])
            self.solutions[key] = {
                "node_id": node_id,
                "canonical_label": params["canonical_label"],
                "description": params["description"],
                "parent_problem_id": params["problem_id"],
                "user_id": params["user_id"],
                "content_hash": params.get("content_hash"),
            }
            return FakeResult({"node_id": node_id})

        if "H6:EDGE_RESOLVED_BY" in query:
            self.edges.add(("RESOLVED_BY", str(params["problem_id"]), str(params["solution_id"]), params["user_id"]))
            return FakeResult(None)

        if "H6:SET_PROBLEM_RESOLVED" in query:
            key = (params["problem_id"], params["user_id"])
            if key in self.problems:
                self.problems[key]["status"] = "resolved"
            return FakeResult(None)

        if "H6:GET_NODE_WITH_NEIGHBORS" in query:
            node_id = str(params["node_id"])
            user_id = params["user_id"]
            record = self._find_node(node_id=node_id, user_id=user_id)
            if record is None:
                return FakeResult(None)

            neighbors: list[dict[str, Any]] = []
            for edge_type, src, dst, uid in self.edges:
                if uid != user_id:
                    continue
                if edge_type not in {"PROPOSED_FOR", "RESOLVED_BY", "BELONGS_TO"}:
                    continue
                neighbor_id = None
                if src == node_id:
                    neighbor_id = dst
                elif dst == node_id:
                    neighbor_id = src
                if not neighbor_id:
                    continue
                neighbor = self._find_node(node_id=neighbor_id, user_id=user_id)
                if not neighbor:
                    continue
                neighbors.append(
                    {
                        "node_id": neighbor_id,
                        "canonical_label": neighbor.get("canonical_label", neighbor_id),
                        "node_type": neighbor.get("node_type", "NODE"),
                        "rel_type": edge_type,
                    }
                )

            return FakeResult(
                {
                    "node_id": node_id,
                    "canonical_label": record.get("canonical_label", node_id),
                    "node_type": record.get("node_type", "NODE"),
                    "context_brief": record.get("context_brief", ""),
                    "status": record.get("status", "unknown"),
                    "recurrence_count": record.get("recurrence_count", 0),
                    "neighbors": neighbors,
                }
            )

        return FakeResult(None)

    def _find_node(self, node_id: str, user_id: str) -> dict[str, Any] | None:
        problem = self.problems.get((node_id, user_id))
        if problem:
            return {
                "node_id": node_id,
                "canonical_label": problem.get("canonical_label", node_id),
                "node_type": "PROBLEM",
                "context_brief": problem.get("context_brief", ""),
                "status": problem.get("status", "open"),
                "recurrence_count": problem.get("recurrence_count", 0),
            }

        for (label, uid), concept in self.concepts.items():
            if uid == user_id and concept.get("node_id") == node_id:
                return {
                    "node_id": node_id,
                    "canonical_label": concept.get("canonical_label", label),
                    "node_type": "CONCEPT",
                    "context_brief": concept.get("description", ""),
                    "status": "unknown",
                }

        for (_, _, uid), solution in self.solutions.items():
            if uid == user_id and solution.get("node_id") == node_id:
                return {
                    "node_id": node_id,
                    "canonical_label": solution.get("canonical_label", node_id),
                    "node_type": "SOLUTION",
                    "context_brief": solution.get("description", ""),
                    "status": "resolved" if solution.get("worked") else "unknown",
                }

        return None


class FakeChroma:
    def __init__(self, query_returns: Any | None = None) -> None:
        self.query_returns = query_returns if query_returns is not None else {"ids": [[]], "distances": [[]], "metadatas": [[]]}
        self.query_calls: list[dict[str, Any]] = []
        self.upserts: list[dict[str, Any]] = []

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.query_calls.append(kwargs)
        if isinstance(self.query_returns, list):
            if self.query_returns:
                return self.query_returns.pop(0)
            return {"ids": [[]], "distances": [[]], "metadatas": [[]]}
        return self.query_returns

    def upsert(self, **kwargs: Any) -> None:
        self.upserts.append(kwargs)


@pytest.fixture
def mock_neo4j() -> FakeNeo4j:
    return FakeNeo4j()


@pytest.fixture
def mock_chroma() -> FakeChroma:
    return FakeChroma()
