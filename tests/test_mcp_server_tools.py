from __future__ import annotations

import asyncio
from typing import Any

from core.mcp_server import server
from core.mcp_server.models import StoreSessionResponse
from core.mcp_server.tokens import mint_mcp_token


class FakeResult:
    def __init__(self, record: dict[str, Any] | None = None) -> None:
        self.record = record

    def single(self) -> dict[str, Any] | None:
        return self.record


class StatusNeo4j:
    def __init__(self) -> None:
        self.query_log: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> FakeResult:
        self.query_log.append((query, params))
        if "RETURN 1 AS ok" in query:
            return FakeResult({"ok": 1})
        if "count(n) AS node_count" in query:
            return FakeResult({"node_count": 3})
        if "collect(DISTINCT label) AS labels" in query:
            return FakeResult({"labels": ["Session", "Entity", "Checkpoint"]})
        if "CREATE (c:Checkpoint:Entity" in query:
            return FakeResult(None)
        return FakeResult(None)


class StatusChroma:
    def count_collections(self) -> int:
        return 2


def test_complete_conversation_worth_storing_false_skips_storage(monkeypatch) -> None:
    async def fail_store_session(**_kwargs) -> StoreSessionResponse:
        raise AssertionError("storage should not run")

    monkeypatch.setattr(server, "handle_store_session", fail_store_session)

    response = asyncio.run(
        server.complete_conversation.fn(
            transcript="hello",
            source="codex",
            worth_storing=False,
        )
    )

    assert response == {"stored": False, "reason": "caller marked not worth storing"}


def test_complete_conversation_passes_structured_fields(monkeypatch) -> None:
    captured = {}

    async def fake_store_session(req, **_kwargs) -> StoreSessionResponse:
        captured["req"] = req
        return StoreSessionResponse(session_id="session-1", insights_stored=1)

    monkeypatch.setattr(server, "handle_store_session", fake_store_session)
    monkeypatch.setattr(server, "get_neo4j", lambda: object())
    monkeypatch.setattr(server, "get_chroma", lambda: object())
    monkeypatch.setattr(server, "get_llm", lambda: None)
    monkeypatch.setattr(server, "get_postgres_store", lambda: None)

    response = asyncio.run(
        server.complete_conversation.fn(
            transcript="We fixed the callback.",
            source="codex",
            user_email="dev@example.com",
            summary="Fixed OAuth callback handling.",
            key_entities=["auth/callback.ts"],
            decisions=["Keep callback routing in the API layer."],
            problems_solved=["Redirect URI mismatch."],
            worth_storing=True,
            session_duration_turns=4,
        )
    )

    req = captured["req"]
    assert response["stored"] is True
    assert req.summary == "Fixed OAuth callback handling."
    assert req.key_entities == ["auth/callback.ts"]
    assert req.decisions == ["Keep callback routing in the API layer."]
    assert req.problems_solved == ["Redirect URI mismatch."]
    assert req.worth_storing is True
    assert req.session_duration_turns == 4


def test_checkpoint_context_writes_checkpoint_node(monkeypatch) -> None:
    neo4j = StatusNeo4j()
    monkeypatch.setattr(server, "_NEO4J_CLIENT", neo4j)

    response = asyncio.run(
        server.checkpoint_context.fn(
            note="Root cause was middleware order.",
            user_email="dev@example.com",
            source="codex",
        )
    )

    assert response["checkpointed"] is True
    query, params = neo4j.query_log[-1]
    assert "CREATE (c:Checkpoint:Entity" in query
    assert params["type"] == "checkpoint"
    assert params["note"] == "Root cause was middleware order."
    assert params["user_email"] == "dev@example.com"
    assert params["source"] == "codex"


def test_orange_status_returns_structured_health_and_token_expiry(monkeypatch) -> None:
    monkeypatch.setenv("ORANGE_MCP_SIGNING_SECRET", "test-secret")
    monkeypatch.setenv("NEO4J_URI", "bolt://backend:7687")
    monkeypatch.setenv("FRONTEND_NEO4J_URI", "bolt://backend:7687")
    monkeypatch.setattr(server, "_NEO4J_CLIENT", StatusNeo4j())
    monkeypatch.setattr(server, "_CHROMA_CLIENT", StatusChroma())
    token = mint_mcp_token("dev@example.com", expires_in_days=5)
    context_token = server._REQUEST_BEARER_TOKEN.set(token)

    try:
        response = asyncio.run(server.orange_status.fn())
    finally:
        server._REQUEST_BEARER_TOKEN.reset(context_token)

    assert response["neo4j"] == {
        "reachable": True,
        "node_count": 3,
        "expected_labels_present": True,
    }
    assert response["chroma"] == {"reachable": True, "collection_count": 2}
    assert response["auth"]["token_present"] is True
    assert response["auth"]["token_valid"] is True
    assert response["auth"]["user_email"] == "dev@example.com"
    assert response["auth"]["token_expires_at"]
    assert response["auth"]["days_until_expiry"] <= 5
    assert response["mode"] == "remote"
    assert response["neo4j_shared_with_frontend"] is True
    assert "recall_memory" in response["tool_list"]
    assert "checkpoint_context" in response["tool_list"]
    assert response["warnings"] == [
        f"MCP token expires in {response['auth']['days_until_expiry']} days. Re-authenticate at /mcp."
    ]


def test_orange_instructions_resource_content() -> None:
    content = server.orange_instructions.fn()

    assert content.startswith("## Orange Memory Protocol")
    assert "Call recall_memory with a short query" in content
    assert "Call checkpoint_context whenever:" in content
    assert "Do NOT call complete_conversation mid-session." in content
