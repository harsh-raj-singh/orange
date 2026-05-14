from __future__ import annotations

import asyncio

from core.agents import classifier
from core.graph_schema_v2 import SourceType
from core.source_registry import ConversationType


def test_classify_debugging_transcript() -> None:
    transcript = """
    User: My FastAPI endpoint throws a CORS error.
    Assistant: Add CORSMiddleware.
    User: It still fails after adding middleware.
    """.strip()

    async def fake_call_llm_json(prompt: str) -> dict[str, object]:
        assert "Source context: cursor" in prompt
        assert "CORS error" in prompt
        return {
            "conversation_type": "debugging",
            "confidence": 0.94,
            "reasoning": "User is troubleshooting a concrete runtime error.",
        }

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(classifier, "call_llm_json", fake_call_llm_json)
    try:
        result = asyncio.run(classifier.classify_transcript(transcript, SourceType.CURSOR))
    finally:
        monkeypatch.undo()

    assert result.conversation_type == ConversationType.DEBUGGING
    assert result.confidence == 0.94


def test_classify_brainstorm_transcript() -> None:
    transcript = """
    User: Should we use Kafka or RabbitMQ for event streaming?
    Assistant: Let's compare throughput and operability.
    """.strip()

    async def fake_call_llm_json(prompt: str) -> dict[str, object]:
        assert "Source context: slack" in prompt
        return {
            "conversation_type": "brainstorm",
            "confidence": 0.88,
            "reasoning": "The conversation is exploring architecture options.",
        }

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(classifier, "call_llm_json", fake_call_llm_json)
    try:
        result = asyncio.run(classifier.classify_transcript(transcript, SourceType.SLACK))
    finally:
        monkeypatch.undo()

    assert result.conversation_type == ConversationType.BRAINSTORM
    assert result.confidence == 0.88


def test_low_confidence_uses_source_fallback() -> None:
    transcript = "User: maybe this is a bug or maybe just design, not sure."

    async def fake_call_llm_json(prompt: str) -> dict[str, object]:
        return {
            "conversation_type": "qa",
            "confidence": 0.41,
            "reasoning": "Ambiguous transcript with mixed intent.",
        }

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(classifier, "call_llm_json", fake_call_llm_json)
    try:
        result = asyncio.run(classifier.classify_transcript(transcript, SourceType.CURSOR))
    finally:
        monkeypatch.undo()

    # Cursor default in source registry is debugging.
    assert result.conversation_type == ConversationType.DEBUGGING
    assert result.confidence == 0.41
    assert "fallback" in result.reasoning.lower()
