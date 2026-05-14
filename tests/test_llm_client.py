from __future__ import annotations

import asyncio
from types import SimpleNamespace

from core.agents import llm_client


def test_call_llm_json_reuses_singleton_client(monkeypatch) -> None:
    class FakeAsyncOpenAI:
        instances_created = 0

        def __init__(self, api_key: str, base_url: str | None = None):
            type(self).instances_created += 1
            self.api_key = api_key
            self.base_url = base_url
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        async def _create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
            )

    monkeypatch.setattr(llm_client, "AsyncOpenAI", FakeAsyncOpenAI)
    llm_client._CLIENT = None
    llm_client._CLIENT_SETTINGS = None

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("NVIDIA_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    first = asyncio.run(llm_client.call_llm_json("return json"))
    second = asyncio.run(llm_client.call_llm_json("return json again"))

    assert first == {"ok": True}
    assert second == {"ok": True}
    assert FakeAsyncOpenAI.instances_created == 1
