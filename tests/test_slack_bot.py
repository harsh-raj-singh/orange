from __future__ import annotations

from datetime import datetime, timezone

from core.slack_bot import RecordedMessage, RecordingSession, build_store_request_from_session


def test_slack_recording_builds_scoped_store_session_request() -> None:
    session = RecordingSession(
        session_id="slack_T123_C123_20260523120000",
        channel_id="C123",
        channel_name="all-orange",
        team_id="T123",
        team_domain="orange-test",
        started_by="U123",
        started_by_name="Aayush",
        started_by_email="ranaharshraj3@gmail.com",
        started_at="2026-05-23T12:00:00+00:00",
        company="Orange Strategy Labs",
    )
    session.participants["U123"] = {
        "id": "U123",
        "name": "Aayush",
        "email": "ranaharshraj3@gmail.com",
    }
    session.messages.append(
        RecordedMessage(
            user_id="U123",
            name="Aayush",
            email="ranaharshraj3@gmail.com",
            text="For GTM, we should start with founder-led outbound in India.",
            ts="1716465600.000100",
        )
    )

    request = build_store_request_from_session(
        session,
        ended_at=datetime(2026, 5, 23, 12, 10, tzinfo=timezone.utc),
    )

    assert request.source == "slack"
    assert request.user_id == "ranaharshraj3@gmail.com"
    assert request.user_email == "ranaharshraj3@gmail.com"
    assert request.company == "Orange Strategy Labs"
    assert request.org_id == "Orange Strategy Labs"
    assert request.contribute_to_global is True
    assert request.worth_storing is True
    assert request.messages == [
        {
            "role": "user",
            "content": "[Aayush]: For GTM, we should start with founder-led outbound in India.",
        }
    ]
    assert "Turn 1 [user]: [Aayush]" in request.transcript
    assert request.source_url == "https://orange-test.slack.com/archives/C123"
