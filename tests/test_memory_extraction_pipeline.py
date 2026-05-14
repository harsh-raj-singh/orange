from __future__ import annotations

from types import SimpleNamespace

from core.memory_extraction.config import ExtractionConfig
from core.memory_extraction.pipeline import DSPyMemoryExtractor


class DummySummarizer:
    def process(self, chat):
        return {
            "query_summary": "Fix deployment error",
            "response_summary": "Add permission",
            "conversation_type": "problem_solution",
            "key_points": ["permission"],
            "was_successful": True,
        }


class DummyImportance:
    def should_store(self, chat, summaries):
        return {
            "should_store": True,
            "importance_score": 0.9,
            "reason": "important",
            "storage_targets": ["vector", "graph"],
            "tags": ["aws"],
        }


class DummyConceptAgent:
    def extract(self, chat, summaries):
        return {
            "concepts": [{"name": "AWS", "type": "service", "level": 1, "context": "cloud"}],
            "problems": [{"name": "Permission error", "type": "problem", "level": 2, "context": "403"}],
            "solutions": [{"name": "Grant IAM permission", "type": "solution", "level": 3, "context": "policy"}],
            "relationships": [{"source": "AWS", "relation": "HAS_PROBLEM", "target": "Permission error"}],
        }


def _chat(memory_request_reason: str = ""):
    return {
        "chat_id": "chat_test",
        "user_id": "user_test",
        "messages": [
            {"role": "user", "content": "Deploy failed with AccessDeniedException", "timestamp": "2026-02-06T10:00:00+00:00"},
            {"role": "assistant", "content": "Check IAM role permissions", "timestamp": "2026-02-06T10:01:00+00:00"},
            {"role": "user", "content": "It worked after adding lambda:CreateFunction", "timestamp": "2026-02-06T10:02:00+00:00"},
        ],
        "memory_request_reason": memory_request_reason,
        "memory_request_aspects": ["error messages", "solution steps"] if memory_request_reason else [],
    }


def _extractor(config: ExtractionConfig):
    return DSPyMemoryExtractor(
        llm=SimpleNamespace(),
        config=config,
        summarization_agent=DummySummarizer(),
        importance_agent=DummyImportance(),
        concept_agent=DummyConceptAgent(),
    )


def test_legacy_path_when_disabled():
    cfg = ExtractionConfig(USE_DSPY_EXTRACTION=False, FALLBACK_TO_LEGACY=True, DUAL_WRITE_MODE=False)
    extractor = _extractor(cfg)

    result = extractor.extract_chat_memory(_chat())

    assert result["memory_payload"]["type"] == "legacy"


def test_fallback_to_legacy_on_dspy_failure(monkeypatch):
    cfg = ExtractionConfig(USE_DSPY_EXTRACTION=True, FALLBACK_TO_LEGACY=True, DUAL_WRITE_MODE=False)
    extractor = _extractor(cfg)
    monkeypatch.setattr(extractor, "_dspy_extract", lambda chat: (_ for _ in ()).throw(RuntimeError("boom")))

    result = extractor.extract_chat_memory(_chat())

    assert result["memory_payload"]["type"] == "legacy"


def test_minimal_fallback_when_no_legacy_fallback(monkeypatch):
    cfg = ExtractionConfig(USE_DSPY_EXTRACTION=True, FALLBACK_TO_LEGACY=False, DUAL_WRITE_MODE=False)
    extractor = _extractor(cfg)
    monkeypatch.setattr(extractor, "_dspy_extract", lambda chat: (_ for _ in ()).throw(RuntimeError("boom")))

    result = extractor.extract_chat_memory(_chat())

    assert result["memory_payload"]["type"] == "fallback"
    assert result["extraction_confidence"] == 0.0


def test_dual_write_comparison_called(monkeypatch):
    cfg = ExtractionConfig(USE_DSPY_EXTRACTION=True, FALLBACK_TO_LEGACY=True, DUAL_WRITE_MODE=True)
    extractor = _extractor(cfg)

    monkeypatch.setattr(extractor, "_dspy_extract", lambda chat: extractor._create_minimal_fallback(chat, "x"))

    called = {"value": False}

    def _mark(*args, **kwargs):
        called["value"] = True

    monkeypatch.setattr(extractor, "_log_comparison", _mark)

    extractor.extract_chat_memory(_chat())

    assert called["value"] is True


def test_retry_success_after_failure(monkeypatch):
    cfg = ExtractionConfig(USE_DSPY_EXTRACTION=True, FALLBACK_TO_LEGACY=False, DUAL_WRITE_MODE=False, MAX_EXTRACTION_RETRIES=2)
    extractor = _extractor(cfg)

    state = {"count": 0}

    def _maybe_fail(chat):
        state["count"] += 1
        if state["count"] == 1:
            raise RuntimeError("temporary")
        return extractor._create_minimal_fallback(chat, "done")

    monkeypatch.setattr(extractor, "_dspy_extract_once", _maybe_fail)

    result = extractor._dspy_extract(_chat())
    assert state["count"] == 2
    assert result["memory_payload"]["type"] == "fallback"


def test_memory_request_override_forces_extraction(monkeypatch):
    cfg = ExtractionConfig(USE_DSPY_EXTRACTION=True, FALLBACK_TO_LEGACY=False, DUAL_WRITE_MODE=False)
    extractor = _extractor(cfg)

    monkeypatch.setattr(
        extractor.classifier,
        "forward",
        lambda conversation, metadata: {
            "conversation_type": "learning",
            "should_extract": False,
            "extraction_depth": "shallow",
            "reasoning": "trivial",
        },
    )
    monkeypatch.setattr(
        extractor,
        "extract_type_payload",
        lambda conversation_type, conversation, metadata: {"type": "learning", "topic": "forced"},
    )
    monkeypatch.setattr(extractor, "capture_negative_paths", lambda c, p: [])
    monkeypatch.setattr(extractor, "extract_concept_graph", lambda c, p: {"concepts": [], "relationships": []})

    result = extractor._dspy_extract_once(_chat(memory_request_reason="Remember this debugging path"))

    assert result["processing_state"] == "processed"
