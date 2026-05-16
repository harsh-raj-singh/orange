from __future__ import annotations

import asyncio

import pytest

from core.mcp_server.handlers import (
    _STORE_SESSION_CACHE,
    handle_ping_context,
    handle_resolve_problem,
    handle_store_session,
)
from core.mcp_server.models import (
    PingContextRequest,
    ResolveProblemRequest,
    StoreSessionRequest,
)


@pytest.fixture(autouse=True)
def clear_store_session_cache() -> None:
    _STORE_SESSION_CACHE.clear()


def test_ping_context_returns_context_blocks(mock_neo4j, mock_chroma) -> None:
    mock_neo4j.problems[("p1", "u1")] = {
        "node_id": "p1",
        "canonical_label": "fastapi cors middleware order",
        "context_brief": "middleware applied after route registration causing options 403",
        "status": "resolved",
    }
    mock_neo4j.problems[("p2", "u1")] = {
        "node_id": "p2",
        "canonical_label": "redis connection pool exhaustion",
        "context_brief": "pool hitting max connections under load",
        "status": "open",
    }
    mock_neo4j.solutions[("move corsmiddleware before include_router", "p1", "u1")] = {
        "node_id": "s1",
        "canonical_label": "move corsmiddleware before include_router",
        "description": "move corsmiddleware before include_router",
        "worked": True,
    }
    mock_neo4j.edges.add(("RESOLVED_BY", "p1", "s1", "u1"))

    mock_chroma.query_returns = {
        "ids": [["p1", "p2"]],
        "distances": [[0.11, 0.22]],
        "metadatas": [[
            {"user_id": "u1", "node_type": "Problem", "canonical_label": "fastapi cors middleware order"},
            {"user_id": "u1", "node_type": "Problem", "canonical_label": "redis connection pool exhaustion"},
        ]],
    }

    req = PingContextRequest(query="cors problem", user_id="u1", source="cursor")
    resp = asyncio.run(handle_ping_context(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert len(resp.matched_nodes) > 0
    assert any(n.node_type == "Problem" for n in resp.matched_nodes)
    assert resp.matched_nodes[0].node_data.get("canonical_label") is not None
    assert len(resp.node_ids_used) > 0


def test_ping_context_respects_token_budget(mock_neo4j, mock_chroma) -> None:
    ids: list[str] = []
    metadatas: list[dict] = []
    for idx in range(10):
        node_id = f"p{idx}"
        ids.append(node_id)
        metadatas.append({"user_id": "u1", "node_type": "Problem", "canonical_label": f"problem {idx}"})
        mock_neo4j.problems[(node_id, "u1")] = {
            "node_id": node_id,
            "canonical_label": f"problem {idx}",
            "context_brief": "x" * 2000,
            "status": "open",
        }

    mock_chroma.query_returns = {
        "ids": [ids],
        "distances": [[0.2] * 10],
        "metadatas": [metadatas],
    }

    req = PingContextRequest(query="anything", user_id="u1", source="cursor")
    resp = asyncio.run(handle_ping_context(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert len(resp.matched_nodes) > 0
    assert any(n.node_type == "Problem" for n in resp.matched_nodes)
    assert resp.matched_nodes[0].node_data.get("canonical_label") is not None
    assert len(resp.node_ids_used) > 0


def test_ping_context_hydrates_with_neo4j_node_id_metadata(mock_neo4j, mock_chroma) -> None:
    mock_neo4j.problems[("p-real", "u1")] = {
        "node_id": "p-real",
        "canonical_label": "real graph node",
        "context_brief": "stored under neo4j id, not vector id",
        "status": "open",
    }
    mock_chroma.query_returns = {
        "ids": [["problem_p-real"]],
        "distances": [[0.1]],
        "metadatas": [[
            {
                "user_id": "u1",
                "node_type": "Problem",
                "neo4j_node_id": "p-real",
                "canonical_label": "real graph node",
            }
        ]],
    }

    req = PingContextRequest(query="graph id", user_id="u1", source="cursor")
    resp = asyncio.run(handle_ping_context(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert resp.node_ids_used == ["p-real"]
    assert resp.matched_nodes[0].node_data["canonical_label"] == "real graph node"


def test_ping_context_queries_user_and_global_scopes_with_user_preference(mock_neo4j, mock_chroma) -> None:
    mock_neo4j.problems[("p-user", "u1")] = {
        "node_id": "p-user",
        "canonical_label": "shared cors problem",
        "context_brief": "user-specific details",
        "status": "open",
    }
    mock_neo4j.problems[("p-global", "")] = {
        "node_id": "p-global",
        "canonical_label": "shared cors problem",
        "context_brief": "global details",
        "status": "open",
        "contributed_by": "someone@example.com",
    }
    mock_chroma.query_returns = [
        {
            "ids": [["p-user"]],
            "distances": [[0.1]],
            "metadatas": [[
                {
                    "scope": "user",
                    "user_email": "dev@example.com",
                    "user_id": "u1",
                    "node_type": "Problem",
                    "canonical_label": "shared cors problem",
                }
            ]],
        },
        {
            "ids": [["p-global"]],
            "distances": [[0.2]],
            "metadatas": [[
                {
                    "scope": "global",
                    "node_type": "Problem",
                    "canonical_label": "shared cors problem",
                    "org_id": "acme",
                    "contributed_by": "someone@example.com",
                }
            ]],
        },
    ]

    req = PingContextRequest(
        query="cors problem",
        user_id="u1",
        user_email="dev@example.com",
        org_id="acme",
        source="cursor",
        scope="both",
    )
    resp = asyncio.run(handle_ping_context(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert len(resp.matched_nodes) == 1
    assert resp.matched_nodes[0].source == "user"
    assert resp.matched_nodes[0].also_available_in_global is True
    assert resp.matched_nodes[0].node_data["global_exists"] is True
    assert "contributed_by" not in resp.matched_nodes[0].node_data
    assert mock_chroma.query_calls[0]["where"] == {"scope": "user", "user_email": "dev@example.com"}
    assert mock_chroma.query_calls[1]["where"] == {"scope": "global", "org_id": "acme"}


def test_ping_context_global_scope_hides_contributor_and_uses_global_threshold(mock_neo4j, mock_chroma) -> None:
    mock_neo4j.problems[("p-global", "")] = {
        "node_id": "p-global",
        "canonical_label": "global redis problem",
        "context_brief": "global details",
        "status": "open",
        "contributed_by": "someone@example.com",
    }
    mock_chroma.query_returns = {
        "ids": [["p-global"]],
        "distances": [[0.27]],
        "metadatas": [[
            {
                "scope": "global",
                "node_type": "Problem",
                "canonical_label": "global redis problem",
                "org_id": "acme",
                "contributed_by": "someone@example.com",
            }
        ]],
    }

    req = PingContextRequest(query="redis", user_id="u1", source="cursor", min_score=0.95, scope="global", org_id="acme")
    resp = asyncio.run(handle_ping_context(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert len(resp.matched_nodes) == 1
    assert resp.matched_nodes[0].source == "global"
    assert "contributed_by" not in resp.matched_nodes[0].node_data
    assert mock_chroma.query_calls[0]["where"] == {"scope": "global", "org_id": "acme"}


def test_ping_context_invalid_source_raises(mock_neo4j, mock_chroma) -> None:
    req = PingContextRequest(query="x", user_id="u1", source="nonexistent_tool")
    with pytest.raises(ValueError, match="source"):
        asyncio.run(handle_ping_context(req, neo4j=mock_neo4j, chroma=mock_chroma))


def test_store_session_returns_summary(monkeypatch: pytest.MonkeyPatch, mock_neo4j, mock_chroma) -> None:
    calls: list[dict] = []

    async def fake_run_extraction_pipeline(**kwargs) -> dict:
        calls.append(kwargs)
        return {"problems_created": 1, "problems_merged": 0, "solutions_written": 1}

    monkeypatch.setattr("core.mcp_server.handlers.run_extraction_pipeline", fake_run_extraction_pipeline)

    req = StoreSessionRequest(
        transcript="we had a cors problem and fixed it by moving middleware",
        source="cursor",
        user_id="u1",
        session_id="sess-abc",
    )
    resp = asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))

    assert resp.session_id == "sess-abc"
    assert resp.problems_created == 1
    assert resp.problems_merged == 0
    assert resp.solutions_written == 1
    assert calls[0]["source"].value == "cursor"


def test_store_session_records_normalized_session_in_postgres(
    monkeypatch: pytest.MonkeyPatch,
    mock_neo4j,
    mock_chroma,
) -> None:
    class FakePostgresStore:
        def __init__(self) -> None:
            self.recorded = []
            self.statuses = []

        def record_normalized_session(self, normalized, *, status: str):
            self.recorded.append((normalized, status))
            return type("Stored", (), {"ingestion_id": "ing-1"})()

        def mark_session_status(self, *, ingestion_id: str, status: str) -> None:
            self.statuses.append((ingestion_id, status))

    async def fake_run_extraction_pipeline(**kwargs) -> dict:
        return {"problems_created": 0, "problems_merged": 0, "solutions_written": 0}

    monkeypatch.setattr("core.mcp_server.handlers.run_extraction_pipeline", fake_run_extraction_pipeline)

    store = FakePostgresStore()
    req = StoreSessionRequest(
        source="cursor",
        user_id="u1",
        session_id="sess-postgres",
        org_id="org-1",
        messages=[{"role": "user", "content": "store this normalized session"}],
    )

    resp = asyncio.run(
        handle_store_session(
            req,
            neo4j=mock_neo4j,
            chroma=mock_chroma,
            llm=None,
            postgres_store=store,
        )
    )

    assert resp.session_id == "sess-postgres"
    assert store.recorded[0][0].org_id == "org-1"
    assert store.recorded[0][0].message_count == 1
    assert store.recorded[0][1] == "received"
    assert store.statuses == [("ing-1", "processed")]


def test_store_session_idempotent(monkeypatch: pytest.MonkeyPatch, mock_neo4j, mock_chroma) -> None:
    calls = {"count": 0}

    async def fake_run_extraction_pipeline(**kwargs) -> dict:
        calls["count"] += 1
        return {"problems_created": 1, "problems_merged": 0, "solutions_written": 0}

    monkeypatch.setattr("core.mcp_server.handlers.run_extraction_pipeline", fake_run_extraction_pipeline)

    req = StoreSessionRequest(transcript="...", source="cursor", user_id="u1", session_id="sess-xyz")
    resp1 = asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))
    resp2 = asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))

    assert resp1.problems_created == resp2.problems_created
    assert calls["count"] == 1


def test_store_session_rejects_empty_transcript(mock_neo4j, mock_chroma) -> None:
    req = StoreSessionRequest(transcript="", source="cursor", user_id="u1", session_id="s1")
    with pytest.raises(ValueError, match="transcript"):
        asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))


def test_resolve_problem_writes_edge(mock_neo4j, mock_chroma) -> None:
    mock_neo4j.problems[("p1", "u1")] = {
        "node_id": "p1",
        "canonical_label": "fastapi cors middleware order",
        "context_brief": "middleware after router include",
        "status": "open",
    }

    req = ResolveProblemRequest(
        session_id="sess-1",
        user_id="u1",
        problem_label="fastapi cors middleware order",
        solution_that_worked="move CORSMiddleware before include_router",
    )
    resp = asyncio.run(handle_resolve_problem(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert resp.resolved is True
    assert resp.problem_node_id is not None
    assert ("RESOLVED_BY", resp.problem_node_id, resp.solution_node_id, "u1") in mock_neo4j.edges


def test_resolve_problem_unknown_label(mock_neo4j, mock_chroma) -> None:
    req = ResolveProblemRequest(
        session_id="s1",
        user_id="u1",
        problem_label="nonexistent problem",
        solution_that_worked="anything",
    )
    resp = asyncio.run(handle_resolve_problem(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert resp.resolved is False
    assert resp.problem_node_id is None
