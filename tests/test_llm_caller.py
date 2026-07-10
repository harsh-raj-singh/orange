from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from core.agents import llm_caller
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


def test_resolve_llm_config_is_cached_after_first_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_caller, "_LLM_CONFIG", None)
    monkeypatch.setenv("OPENAI_API_KEY", "first-key")
    monkeypatch.setenv("OPENAI_MODEL", "first-model")

    first = llm_caller._resolve_llm_config()

    monkeypatch.setenv("OPENAI_API_KEY", "second-key")
    monkeypatch.setenv("OPENAI_MODEL", "second-model")

    assert first == ("first-key", "first-model", None)
    assert llm_caller._resolve_llm_config() == first


def test_call_llm_json_backs_off_without_writing_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeCompletions:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **_request):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("rate limited")
            message = SimpleNamespace(content='{"ok": true}')
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    fake_completions = FakeCompletions()
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=fake_completions))
    sleep_attempts: list[int] = []

    async def fake_sleep(attempt: int) -> None:
        sleep_attempts.append(attempt)

    monkeypatch.setattr(llm_caller, "_LLM_CONFIG", ("test-key", "test-model", None))
    monkeypatch.setattr(llm_caller, "_get_client", lambda **_kwargs: fake_client)
    monkeypatch.setattr(llm_caller, "_sleep_before_retry", fake_sleep)

    result = asyncio.run(llm_caller.call_llm_json("system", "user"))

    assert result == {"ok": True}
    assert sleep_attempts == [1, 2]
    assert capsys.readouterr().out == ""
