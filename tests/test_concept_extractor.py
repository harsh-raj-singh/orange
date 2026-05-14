from __future__ import annotations

import asyncio

from core.agents import concept_extractor
from core.graph_schema_v2 import ConceptCategory


FASTAPI_TRANSCRIPT = """
User: I'm getting a CORS error in my FastAPI app.
Assistant: Add CORSMiddleware and check order.
User: Reordering middleware fixed it.
""".strip()


def test_extract_concepts_fastapi_cors() -> None:
    async def fake_call_llm_json(prompt: str) -> dict[str, object]:
        assert "reusable concepts" in prompt.lower()
        return {
            "concepts": [
                {
                    "canonical_label": "fastapi",
                    "category": "framework",
                    "parent_concept": None,
                },
                {
                    "canonical_label": "cors",
                    "category": "protocol",
                    "parent_concept": "http",
                },
            ]
        }

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(concept_extractor, "call_llm_json", fake_call_llm_json)
    try:
        result = asyncio.run(concept_extractor.extract_concepts(FASTAPI_TRANSCRIPT))
    finally:
        monkeypatch.undo()

    labels = {item.canonical_label for item in result.concepts}
    assert "fastapi" in labels
    assert "cors" in labels

    fastapi = next(item for item in result.concepts if item.canonical_label == "fastapi")
    cors = next(item for item in result.concepts if item.canonical_label == "cors")

    assert fastapi.category == ConceptCategory.FRAMEWORK
    assert cors.category == ConceptCategory.PROTOCOL
    assert cors.parent_concept in (None, "http")
