from __future__ import annotations

import asyncio

from core.mcp_server import server
from core.mcp_server.models import StoreSessionResponse


def _tool_callable(tool):
    """Support FastMCP 2 tool wrappers and FastMCP 3 decorated functions."""

    return getattr(tool, "fn", tool)


def test_complete_conversation_worth_storing_false_skips_storage(monkeypatch) -> None:
    async def fail_store_session(**_kwargs) -> StoreSessionResponse:
        raise AssertionError("storage should not run")

    monkeypatch.setattr(server, "handle_store_session", fail_store_session)

    response = asyncio.run(
        _tool_callable(server.complete_conversation)(
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
    monkeypatch.setattr(server, "get_llm", lambda: None)
    monkeypatch.setattr(server, "get_postgres_store", lambda: object())

    response = asyncio.run(
        _tool_callable(server.complete_conversation)(
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


def test_checkpoint_context_writes_postgres_insight(monkeypatch) -> None:
    captured = {}

    class FakeRepository:
        def checkpoint_context(self, note, **kwargs):
            captured.update({"note": note, **kwargs})
            return {"checkpointed": True, "node_id": "checkpoint-1"}

    monkeypatch.setattr(server, "get_postgres_store", lambda: FakeRepository())

    response = asyncio.run(
        _tool_callable(server.checkpoint_context)(
            note="Root cause was middleware order.",
            user_email="dev@example.com",
            source="codex",
        )
    )

    assert response["checkpointed"] is True
    assert captured["note"] == "Root cause was middleware order."
    assert captured["user_email"] == "dev@example.com"
    assert captured["source"] == "codex"


def test_orange_status_returns_postgres_and_oauth_health(monkeypatch) -> None:
    monkeypatch.setattr(server, "_check_postgres", lambda: {
        "reachable": True,
        "pgvector_version": "0.8.2",
        "session_count": 2,
        "insight_count": 3,
        "queued_jobs": 0,
        "dead_letter_jobs": 0,
    })
    monkeypatch.setattr(server, "_auth_status", lambda: {
        "provider": "supabase_oauth",
        "configured": True,
        "authenticated": True,
        "subject": "user-1",
        "user_email": "dev@example.com",
        "token_expires_at": "2026-07-10T18:00:00+00:00",
    })

    response = asyncio.run(_tool_callable(server.orange_status)())

    assert response["storage"] == "supabase-postgres-pgvector"
    assert response["postgres"]["reachable"] is True
    assert response["postgres"]["pgvector_version"] == "0.8.2"
    assert response["auth"]["authenticated"] is True
    assert "recall_memory" in response["tool_list"]
    assert "checkpoint_context" in response["tool_list"]
    assert "get_job_status" in response["tool_list"]
    assert response["warnings"] == []


def test_orange_instructions_resource_content() -> None:
    content = _tool_callable(server.orange_instructions)()

    assert content.startswith("## Orange Memory Protocol")
    assert "Call recall_memory with a short query" in content
    assert "Call checkpoint_context whenever:" in content
    assert "Do NOT call complete_conversation mid-session." in content
