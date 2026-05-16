from __future__ import annotations

from core.agents.orchestrator import _session_node_from_normalized
from core.ingestion import SessionIngestionRequest, normalize_ingestion_request


def test_normalizes_messages_into_turn_transcript_and_metadata() -> None:
    normalized = normalize_ingestion_request(
        SessionIngestionRequest(
            source="claude",
            user_id="dev_123",
            user_email="dev@example.com",
            session_id="abc",
            external_session_id="claude-session-abc",
            org_id="org_1",
            started_at="2026-05-15T09:10:00Z",
            ended_at="2026-05-15T09:20:00Z",
            participants=[{"id": "dev_123"}, {"name": "assistant"}],
            messages=[
                {
                    "role": "user",
                    "content": "The FastAPI CORS preflight is failing.",
                    "timestamp": "2026-05-15T09:10:00Z",
                    "author_id": "dev_123",
                },
                {
                    "role": "agent",
                    "content": "Move CORSMiddleware before route registration.",
                    "author_name": "assistant",
                },
            ],
            client_name="claude-code",
            client_version="2.1.0",
            source_url="claude://session/abc",
        )
    )

    assert normalized.session_id == "abc"
    assert normalized.session_node_id == "session_abc"
    assert normalized.source.value == "claude"
    assert normalized.user_id == "dev_123"
    assert normalized.user_email == "dev@example.com"
    assert normalized.org_id == "org_1"
    assert normalized.participant_ids == ["dev_123", "assistant"]
    assert normalized.transcript == (
        "Turn 1 [user]: The FastAPI CORS preflight is failing.\n"
        "Turn 2 [assistant]: Move CORSMiddleware before route registration."
    )
    assert normalized.client_name == "claude-code"
    assert normalized.client_version == "2.1.0"
    assert normalized.source_url == "claude://session/abc"
    assert normalized.ingestion_metadata()["user_email"] == "dev@example.com"


def test_normalizes_simple_transcript_and_generates_stable_identity() -> None:
    first = normalize_ingestion_request(
        SessionIngestionRequest(
            source="cursor",
            session_id=None,
            user_id="dev_123",
            transcript="User: Import fails\nAssistant: Check package exports",
            started_at="2026-05-15T09:10:00Z",
        )
    )
    second = normalize_ingestion_request(
        SessionIngestionRequest(
            source="cursor",
            session_id=None,
            user_id="dev_123",
            transcript="User: Import fails\nAssistant: Check package exports",
            started_at="2026-05-15T09:10:00Z",
        )
    )

    assert first.session_id == second.session_id
    assert first.transcript == "User: Import fails\nAssistant: Check package exports"


def test_session_node_defaults_missing_started_at_to_ingested_at() -> None:
    normalized = normalize_ingestion_request(
        SessionIngestionRequest(
            source="cursor",
            user_id="dev_123",
            session_id="missing-start",
            messages=[{"role": "user", "content": "CORS preflight fails"}],
        )
    )

    session_node = _session_node_from_normalized(normalized, "CORS preflight fails")

    assert session_node.started_at == normalized.ingested_at
