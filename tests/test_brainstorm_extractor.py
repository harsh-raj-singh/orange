from __future__ import annotations

import asyncio

from core.agents import brainstorm_extractor


def test_extract_brainstorm_decision() -> None:
    transcript = """
    User: Should we use Postgres or Mongo for analytics events?
    Assistant: Mongo can flex with variable schemas.
    User: Let's go with Mongo for now.
    """.strip()

    async def fake_call_llm_json(prompt: str) -> dict[str, object]:
        assert "do not emit problem nodes".lower() in prompt.lower()
        return {
            "decisions": [
                {
                    "label": "use mongo for analytics events",
                    "rationale": "Flexible schema makes iteration faster.",
                    "alternatives": ["postgres"],
                }
            ],
            "options_considered": ["postgres", "mongo"],
            "concepts": ["mongo", "postgres"],
            "topic_label": "analytics event store",
        }

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(brainstorm_extractor, "call_llm_json", fake_call_llm_json)
    try:
        result = asyncio.run(brainstorm_extractor.extract_brainstorm(transcript))
    finally:
        monkeypatch.undo()

    assert len(result.decisions) == 1
    assert "mongo" in result.decisions[0].label
    assert "postgres" in result.decisions[0].alternatives
