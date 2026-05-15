from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.graph_schema_v2 import SourceType
from core.ingestion import SessionIngestionRequest, normalize_session_request


def test_normalize_session_request_keeps_source_metadata_and_turns() -> None:
    normalized = normalize_session_request(
        SessionIngestionRequest(
            source="claude",
            session_id="thread-123",
            user_id="user-1",
            org_id="org-1",
            started_at="2026-05-15T10:00:00Z",
            ended_at=datetime(2026, 5, 15, 10, 2, tzinfo=timezone.utc),
            participants=[{"id": "user-1", "name": "Harsh", "role": "user"}, "assistant-1"],
            client_name="claude-code",
            client_version="1.2.3",
            source_url="https://example.test/thread-123",
            tool_metadata={"tool": "mcp"},
            messages=[
                {
                    "id": "m1",
                    "role": "human",
                    "content": "Why does this migration fail?",
                    "timestamp": "2026-05-15T10:00:00Z",
                    "user_id": "user-1",
                },
                {
                    "id": "m2",
                    "role": "ai",
                    "content": "The nullable column is being backfilled after the constraint.",
                    "timestamp": "2026-05-15T10:01:00Z",
                    "user_id": "assistant-1",
                },
            ],
        )
    )

    assert normalized.source == SourceType.CLAUDE
    assert normalized.session_id == "thread-123"
    assert normalized.external_session_id == "thread-123"
    assert normalized.user_id == "user-1"
    assert normalized.org_id == "org-1"
    assert normalized.client_name == "claude-code"
    assert normalized.client_version == "1.2.3"
    assert normalized.source_url == "https://example.test/thread-123"
    assert normalized.participant_ids == ["user-1", "assistant-1"]
    assert normalized.message_count == 2
    assert normalized.turns[0].role == "user"
    assert normalized.turns[1].role == "assistant"
    assert normalized.transcript.startswith("Turn 1 [user]: Why does this migration fail?")
    assert normalized.ingestion_metadata()["normalized_turns"][0]["turn_index"] == 1
    assert normalized.ingestion_metadata()["raw_messages"][0]["id"] == "m1"


def test_normalize_session_request_accepts_raw_transcript() -> None:
    normalized = normalize_session_request(
        {
            "source": "cursor",
            "session_id": "sess-1",
            "raw_transcript": "user: fixed the failing test",
        }
    )

    assert normalized.source == SourceType.CURSOR
    assert normalized.transcript == "user: fixed the failing test"


def test_normalize_session_request_requires_messages_or_transcript() -> None:
    with pytest.raises(ValueError, match="messages or raw_transcript"):
        normalize_session_request({"source": "slack", "session_id": "empty"})
