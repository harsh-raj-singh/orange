from __future__ import annotations

from core.agents.llm_caller import _parse_llm_json


def test_parse_llm_json_repairs_invalid_backtick_escapes() -> None:
    raw = '{"summary": "Throw NotFoundException(\\`User ${id} not found\\`) before returning."}'

    parsed = _parse_llm_json(raw)

    assert parsed == {
        "summary": "Throw NotFoundException(`User ${id} not found`) before returning."
    }


def test_parse_llm_json_extracts_object_from_fenced_response() -> None:
    raw = '```json\n{"ok": true, "label": "Slack recording"}\n```'

    parsed = _parse_llm_json(raw)

    assert parsed == {"ok": True, "label": "Slack recording"}
