from __future__ import annotations

import asyncio

import pytest

from core.mcp_server.handlers import _STORE_SESSION_CACHE, handle_recall_memory, handle_store_session
from core.mcp_server.models import RecallMemoryRequest, StoreSessionRequest


@pytest.fixture(autouse=True)
def clear_store_session_cache() -> None:
    _STORE_SESSION_CACHE.clear()


def _add_insight(mock_neo4j, node_id: str, *, label: str, what: str, company: str | None = None) -> None:
    mock_neo4j.insights[node_id] = {
        "display_label": label,
        "display_summary": what,
        "memory_kind": "technical_insight",
        "company": company,
        "what": what,
        "why": None,
        "how": None,
        "outcome": "exploratory",
        "tags": ["test"],
        "raw_session_id": "session-1",
        "session_title": "Session",
        "session_summary": "Summary",
        "similar_insights": [],
    }


def test_recall_memory_returns_insight_context(mock_neo4j, mock_chroma) -> None:
    _add_insight(mock_neo4j, "i1", label="FastAPI CORS middleware order", what="Move CORSMiddleware before routes.")
    mock_chroma.query_returns = {
        "ids": [["insight_i1"]],
        "distances": [[0.11]],
        "metadatas": [[
            {
                "user_id": "u1",
                "scope": "user",
                "node_type": "Insight",
                "neo4j_node_id": "i1",
                "canonical_label": "FastAPI CORS middleware order",
            }
        ]],
    }

    req = RecallMemoryRequest(query="cors problem", user_id="u1", source="cursor")
    resp = asyncio.run(handle_recall_memory(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert len(resp.matched_nodes) == 1
    assert resp.matched_nodes[0].node_type == "Insight"
    assert resp.matched_nodes[0].node_data["display_label"] == "FastAPI CORS middleware order"
    assert resp.node_ids_used == ["i1"]


def test_recall_memory_ignores_legacy_vector_shapes(mock_neo4j, mock_chroma) -> None:
    mock_chroma.query_returns = {
        "ids": [["p1"]],
        "distances": [[0.11]],
        "metadatas": [[{"user_id": "u1", "scope": "user", "node_type": "Problem", "canonical_label": "old"}]],
    }

    req = RecallMemoryRequest(query="old problem", user_id="u1", source="cursor")
    resp = asyncio.run(handle_recall_memory(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert resp.matched_nodes == []
    assert resp.node_ids_used == []


def test_recall_memory_queries_user_and_global_scopes_with_user_preference(mock_neo4j, mock_chroma) -> None:
    _add_insight(mock_neo4j, "i-user", label="Shared CORS insight", what="User-specific details")
    _add_insight(mock_neo4j, "i-global", label="Shared CORS insight", what="Global details", company="Acme")
    mock_chroma.query_returns = [
        {
            "ids": [["insight_i-user"]],
            "distances": [[0.1]],
            "metadatas": [[
                {
                    "scope": "user",
                    "user_email": "dev@example.com",
                    "user_id": "u1",
                    "node_type": "Insight",
                    "neo4j_node_id": "i-user",
                    "canonical_label": "Shared CORS insight",
                }
            ]],
        },
        {
            "ids": [["insight_i-global"]],
            "distances": [[0.2]],
            "metadatas": [[
                {
                    "scope": "global",
                    "node_type": "Insight",
                    "neo4j_node_id": "i-global",
                    "canonical_label": "Shared CORS insight",
                    "org_id": "acme",
                    "contributed_by": "someone@example.com",
                }
            ]],
        },
    ]

    req = RecallMemoryRequest(
        query="cors problem",
        user_id="u1",
        user_email="dev@example.com",
        org_id="acme",
        source="cursor",
        scope="both",
    )
    resp = asyncio.run(handle_recall_memory(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert len(resp.matched_nodes) == 1
    assert resp.matched_nodes[0].source == "user"
    assert resp.matched_nodes[0].also_available_in_global is True
    assert resp.matched_nodes[0].node_data["global_exists"] is True
    assert mock_chroma.query_calls[0]["where"] == {"scope": "user", "user_email": "dev@example.com"}
    assert mock_chroma.query_calls[1]["where"] == {"scope": "global", "org_id": "acme"}


def test_recall_memory_global_scope_uses_requested_threshold(mock_neo4j, mock_chroma) -> None:
    _add_insight(mock_neo4j, "i-global", label="Global Redis Insight", what="Global details", company="Acme")
    mock_chroma.query_returns = {
        "ids": [["insight_i-global"]],
        "distances": [[0.27]],
        "metadatas": [[
            {
                "scope": "global",
                "node_type": "Insight",
                "neo4j_node_id": "i-global",
                "canonical_label": "Global Redis Insight",
                "org_id": "acme",
                "contributed_by": "someone@example.com",
            }
        ]],
    }

    req = RecallMemoryRequest(query="redis", user_id="u1", source="cursor", min_score=0.70, scope="global", org_id="acme")
    resp = asyncio.run(handle_recall_memory(req, neo4j=mock_neo4j, chroma=mock_chroma))

    assert len(resp.matched_nodes) == 1
    assert resp.matched_nodes[0].source == "global"
    assert mock_chroma.query_calls[0]["where"] == {"scope": "global", "org_id": "acme"}


def test_recall_memory_invalid_source_raises(mock_neo4j, mock_chroma) -> None:
    req = RecallMemoryRequest(query="x", user_id="u1", source="nonexistent_tool")
    with pytest.raises(ValueError, match="source"):
        asyncio.run(handle_recall_memory(req, neo4j=mock_neo4j, chroma=mock_chroma))


def test_store_session_returns_summary(monkeypatch: pytest.MonkeyPatch, mock_neo4j, mock_chroma) -> None:
    calls: list[dict] = []

    async def fake_run_extraction_pipeline(**kwargs) -> dict:
        calls.append(kwargs)
        return {"insights_stored": 1}

    monkeypatch.setattr("core.mcp_server.handlers.run_extraction_pipeline", fake_run_extraction_pipeline)

    req = StoreSessionRequest(
        transcript="we had a cors problem and fixed it by moving middleware",
        source="cursor",
        user_id="u1",
        session_id="sess-abc",
    )
    resp = asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))

    assert resp.session_id == "sess-abc"
    assert resp.insights_stored == 1
    assert calls[0]["source"].value == "cursor"


def test_store_session_accepts_codex_source_and_email_identity(
    monkeypatch: pytest.MonkeyPatch,
    mock_neo4j,
    mock_chroma,
) -> None:
    calls: list[dict] = []

    async def fake_run_extraction_pipeline(**kwargs) -> dict:
        calls.append(kwargs)
        return {"insights_stored": 1, "skipped_reason": None}

    monkeypatch.setattr("core.mcp_server.handlers.run_extraction_pipeline", fake_run_extraction_pipeline)

    req = StoreSessionRequest(
        source="codex",
        user_email="dev@example.com",
        company="Acme",
        session_id="codex-session",
        messages=[
            {"role": "user", "content": "Our company uses .md files for memory."},
            {"role": "assistant", "content": "Got it."},
        ],
    )
    resp = asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))

    assert resp.session_id == "codex-session"
    assert resp.insights_stored == 1
    assert calls[0]["source"].value == "codex"
    assert calls[0]["user_id"] == "dev@example.com"
    assert calls[0]["normalized_session"].org_id == "acme"


def test_store_session_passes_structured_completion_context(
    monkeypatch: pytest.MonkeyPatch,
    mock_neo4j,
    mock_chroma,
) -> None:
    calls: list[dict] = []

    async def fake_run_extraction_pipeline(**kwargs) -> dict:
        calls.append(kwargs)
        return {"insights_stored": 1, "skipped_reason": None}

    monkeypatch.setattr("core.mcp_server.handlers.run_extraction_pipeline", fake_run_extraction_pipeline)

    req = StoreSessionRequest(
        source="codex",
        user_email="dev@example.com",
        session_id="structured-session",
        messages=[{"role": "user", "content": "We fixed the auth callback."}],
        summary="Fixed the OAuth callback mismatch.",
        key_entities=["auth/callback.ts", "OAuth adapter"],
        decisions=["Keep the callback route under /api/auth."],
        problems_solved=["Redirect URI mismatch."],
        worth_storing=True,
        session_duration_turns=6,
    )
    resp = asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))

    assert resp.insights_stored == 1
    assert calls[0]["force_worth_storing"] is True
    metadata = calls[0]["normalized_session"].metadata
    assert metadata["summary"] == "Fixed the OAuth callback mismatch."
    assert metadata["key_entities"] == ["auth/callback.ts", "OAuth adapter"]
    assert "Caller-provided structured session summary" in metadata["structured_completion_context"]


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
        return {"insights_stored": 0}

    monkeypatch.setattr("core.mcp_server.handlers.run_extraction_pipeline", fake_run_extraction_pipeline)

    store = FakePostgresStore()
    req = StoreSessionRequest(
        source="cursor",
        user_id="u1",
        session_id="sess-postgres",
        org_id="org-1",
        messages=[{"role": "user", "content": "store this normalized session"}],
    )

    resp = asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None, postgres_store=store))

    assert resp.session_id == "sess-postgres"
    assert store.recorded[0][0].org_id == "org-1"
    assert store.recorded[0][0].message_count == 1
    assert store.recorded[0][1] == "received"
    assert store.statuses == [("ing-1", "processed")]


def test_store_session_idempotent(monkeypatch: pytest.MonkeyPatch, mock_neo4j, mock_chroma) -> None:
    calls = {"count": 0}

    async def fake_run_extraction_pipeline(**kwargs) -> dict:
        calls["count"] += 1
        return {"insights_stored": 1}

    monkeypatch.setattr("core.mcp_server.handlers.run_extraction_pipeline", fake_run_extraction_pipeline)

    req = StoreSessionRequest(transcript="...", source="cursor", user_id="u1", session_id="sess-xyz")
    resp1 = asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))
    resp2 = asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))

    assert resp1.insights_stored == resp2.insights_stored
    assert calls["count"] == 1


def test_store_session_reprocesses_same_session_when_transcript_changes(
    monkeypatch: pytest.MonkeyPatch,
    mock_neo4j,
    mock_chroma,
) -> None:
    calls = {"count": 0}

    async def fake_run_extraction_pipeline(**kwargs) -> dict:
        calls["count"] += 1
        return {"insights_stored": 0}

    monkeypatch.setattr("core.mcp_server.handlers.run_extraction_pipeline", fake_run_extraction_pipeline)

    first = StoreSessionRequest(transcript="turn one", source="cursor", user_id="u1", session_id="sess-xyz")
    second = StoreSessionRequest(transcript="turn one\nturn two", source="cursor", user_id="u1", session_id="sess-xyz")

    asyncio.run(handle_store_session(first, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))
    asyncio.run(handle_store_session(second, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))

    assert calls["count"] == 2


def test_store_session_rejects_empty_transcript(mock_neo4j, mock_chroma) -> None:
    req = StoreSessionRequest(transcript="", source="cursor", user_id="u1", session_id="s1")
    with pytest.raises(ValueError, match="transcript"):
        asyncio.run(handle_store_session(req, neo4j=mock_neo4j, chroma=mock_chroma, llm=None))
