from __future__ import annotations

import asyncio

from core.agents import debug_extractor
from core.agents.debug_extractor import ResolutionStatus


FASTAPI_TRANSCRIPT = """
User: I'm getting a CORS error in my FastAPI app. The frontend
      is on localhost:3000 and backend on localhost:8000.
LLM:  You need to add CORSMiddleware. Here's how: [code snippet]
User: Still getting the error after adding it.
LLM:  Make sure the middleware is added before your router
      includes. Order matters in FastAPI.
User: That fixed it!
""".strip()


def test_extract_debug_fastapi_cors() -> None:
    async def fake_call_llm_json(prompt: str) -> dict[str, object]:
        assert "Extract ALL distinct problems" in prompt
        assert "Extract ALL solutions" in prompt
        return {
            "problems": [
                {
                    "canonical_label": "fastapi cors middleware order",
                    "context_brief": "Frontend on localhost:3000 with FastAPI backend on localhost:8000.",
                    "concepts": ["cors", "fastapi"],
                    "severity": "high",
                    "status": "resolved",
                    "symptom_keywords": ["cors", "middleware", "order"],
                    "solutions": [
                        {
                            "canonical_label": "add corsmiddleware before router includes",
                            "description": "add corsmiddleware before router includes",
                            "tried": True,
                            "worked": True,
                            "confidence": "high",
                        }
                    ],
                }
            ],
            "session_resolution_status": "resolved",
        }

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(debug_extractor, "call_llm_json", fake_call_llm_json)
    try:
        result = asyncio.run(debug_extractor.extract_debug(FASTAPI_TRANSCRIPT))
    finally:
        monkeypatch.undo()

    assert len(result.problems) == 1
    assert result.problems[0].canonical_label == "fastapi cors middleware order"
    assert result.problems[0].solutions[0].worked is True
    assert result.session_resolution_status == ResolutionStatus.RESOLVED
