from __future__ import annotations

import asyncio

from core.agents import runner
from core.agents.brainstorm_extractor import BrainstormExtractionResult
from core.agents.classifier import ClassifierOutput
from core.agents.concept_extractor import ConceptExtractionResult
from core.agents.debug_extractor import DebugExtractionResult, ResolutionStatus
from core.graph_schema_v2 import SourceType
from core.source_registry import ConversationType


def test_run_extraction_debug_flow_cursor() -> None:
    transcript = "User: FastAPI CORS is failing after middleware changes"
    calls: dict[str, object] = {
        "classifier": None,
        "debug": None,
        "brainstorm": None,
        "concept": None,
    }

    async def fake_classify(text: str, source: SourceType) -> ClassifierOutput:
        calls["classifier"] = (text, source)
        return ClassifierOutput(
            conversation_type=ConversationType.DEBUGGING,
            confidence=0.91,
            reasoning="clear runtime error troubleshooting",
        )

    async def fake_debug(text: str) -> DebugExtractionResult:
        calls["debug"] = text
        return DebugExtractionResult(problems=[], session_resolution_status=ResolutionStatus.OPEN)

    async def fake_brainstorm(text: str) -> BrainstormExtractionResult:
        calls["brainstorm"] = text
        return BrainstormExtractionResult(topic_label="should not run")

    async def fake_concepts(text: str) -> ConceptExtractionResult:
        calls["concept"] = text
        return ConceptExtractionResult(concepts=[])

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(runner, "classify_transcript", fake_classify)
    monkeypatch.setattr(runner, "extract_debug", fake_debug)
    monkeypatch.setattr(runner, "extract_brainstorm", fake_brainstorm)
    monkeypatch.setattr(runner, "extract_concepts", fake_concepts)
    try:
        result = asyncio.run(
            runner.run_extraction(
                session_id="s_debug_1",
                transcript=transcript,
                source=SourceType.CURSOR,
            )
        )
    finally:
        monkeypatch.undo()

    assert result.debug_result is not None
    assert result.brainstorm_result is None
    assert result.concept_result is not None

    assert calls["classifier"] == (transcript, SourceType.CURSOR)
    assert calls["debug"] == transcript
    assert calls["concept"] == transcript
    assert calls["brainstorm"] is None


def test_run_extraction_brainstorm_flow_streamlit() -> None:
    transcript = "User: should we use postgres or mongo? I choose mongo."
    calls: dict[str, object] = {
        "classifier": None,
        "debug": None,
        "brainstorm": None,
        "concept": None,
    }

    async def fake_classify(text: str, source: SourceType) -> ClassifierOutput:
        calls["classifier"] = (text, source)
        return ClassifierOutput(
            conversation_type=ConversationType.BRAINSTORM,
            confidence=0.86,
            reasoning="option exploration and selection",
        )

    async def fake_debug(text: str) -> DebugExtractionResult:
        calls["debug"] = text
        return DebugExtractionResult(problems=[], session_resolution_status=ResolutionStatus.OPEN)

    async def fake_brainstorm(text: str) -> BrainstormExtractionResult:
        calls["brainstorm"] = text
        return BrainstormExtractionResult(
            decisions=[],
            options_considered=["postgres", "mongo"],
            concepts=["postgres", "mongo"],
            topic_label="database choice",
        )

    async def fake_concepts(text: str) -> ConceptExtractionResult:
        calls["concept"] = text
        return ConceptExtractionResult(concepts=[])

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(runner, "classify_transcript", fake_classify)
    monkeypatch.setattr(runner, "extract_debug", fake_debug)
    monkeypatch.setattr(runner, "extract_brainstorm", fake_brainstorm)
    monkeypatch.setattr(runner, "extract_concepts", fake_concepts)
    try:
        result = asyncio.run(
            runner.run_extraction(
                session_id="s_brain_1",
                transcript=transcript,
                source=SourceType.STREAMLIT,
            )
        )
    finally:
        monkeypatch.undo()

    assert result.debug_result is None
    assert result.brainstorm_result is not None
    assert result.concept_result is not None

    assert calls["classifier"] == (transcript, SourceType.STREAMLIT)
    assert calls["brainstorm"] == transcript
    assert calls["concept"] == transcript
    assert calls["debug"] is None


def test_run_extraction_concept_failure_does_not_block_debug() -> None:
    transcript = "User: app crashes with import error and asks for fix"

    async def fake_classify(text: str, source: SourceType) -> ClassifierOutput:
        return ClassifierOutput(
            conversation_type=ConversationType.DEBUGGING,
            confidence=0.89,
            reasoning="runtime error troubleshooting",
        )

    async def fake_debug(text: str) -> DebugExtractionResult:
        return DebugExtractionResult(problems=[], session_resolution_status=ResolutionStatus.OPEN)

    async def fake_concepts(text: str) -> ConceptExtractionResult:
        raise RuntimeError("concept extractor unavailable")

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(runner, "classify_transcript", fake_classify)
    monkeypatch.setattr(runner, "extract_debug", fake_debug)
    monkeypatch.setattr(runner, "extract_concepts", fake_concepts)
    try:
        result = asyncio.run(
            runner.run_extraction(
                session_id="s_debug_concept_failure",
                transcript=transcript,
                source=SourceType.CURSOR,
            )
        )
    finally:
        monkeypatch.undo()

    assert result.debug_result is not None
    assert result.brainstorm_result is None
    assert result.concept_result.concepts == []
