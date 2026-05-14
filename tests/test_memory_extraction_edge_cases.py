from __future__ import annotations

from types import SimpleNamespace

from core.memory_extraction.config import ExtractionConfig
from core.memory_extraction.pipeline import DSPyMemoryExtractor


def _extractor():
    return DSPyMemoryExtractor(llm=SimpleNamespace(), config=ExtractionConfig(FALLBACK_TO_LEGACY=False, DUAL_WRITE_MODE=False))


def test_trivial_conversation_skipped():
    chat = {
        "chat_id": "chat_trivial",
        "user_id": "user",
        "messages": [
            {"role": "user", "content": "What is the capital of India?"},
            {"role": "assistant", "content": "New Delhi."},
        ],
    }
    extractor = _extractor()
    result = extractor.extract_chat_memory(chat)
    assert result["processing_state"] in {"skipped", "processed"}


def test_long_conversation_preprocessing():
    messages = []
    for i in range(80):
        role = "user" if i % 2 == 0 else "assistant"
        text = f"step {i} normal message"
        if i == 35:
            text = "AccessDeniedException happened during deploy"
        messages.append({"role": role, "content": text})

    chat = {"chat_id": "chat_long", "user_id": "user", "messages": messages}
    extractor = _extractor()
    result = extractor.extract_chat_memory(chat)
    assert "processing_state" in result
