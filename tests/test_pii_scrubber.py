from __future__ import annotations

import asyncio

from core.agents.pii_scrubber import scrub_pii_transcript


def test_scrubber_fallback_removes_common_pii_and_preserves_technical_details() -> None:
    transcript = (
        "Alice Smith at alice@example.com hit FastAPI ValueError on http://localhost:8000/docs. "
        "Repo path /Users/alice/acme/secret-service failed with token=abc123secret. "
        "Redis was redis://localhost:6379/0 and phone was +1 (415) 555-1212."
    )

    cleaned = asyncio.run(scrub_pii_transcript(transcript, known_pii=["Alice Smith", "acme"]))

    assert "Alice Smith" not in cleaned
    assert "alice@example.com" not in cleaned
    assert "+1 (415) 555-1212" not in cleaned
    assert "/Users/alice" not in cleaned
    assert "abc123secret" not in cleaned
    assert "FastAPI ValueError" in cleaned
    assert "http://localhost:8000/docs" in cleaned
    assert "redis://localhost:6379/0" in cleaned


def test_scrubber_fallback_redacts_nonlocal_urls() -> None:
    cleaned = asyncio.run(
        scrub_pii_transcript(
            "See https://acme.example.com/private and http://127.0.0.1:3000/health",
            known_pii=["acme"],
        )
    )

    assert "acme.example.com" not in cleaned
    assert "[URL]" in cleaned
    assert "http://127.0.0.1:3000/health" in cleaned
