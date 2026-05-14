from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import AsyncOpenAI

_CLIENT: AsyncOpenAI | None = None
_CLIENT_SETTINGS: tuple[str, str | None] | None = None


def _get_client(api_key: str, base_url: str | None) -> AsyncOpenAI:
    global _CLIENT, _CLIENT_SETTINGS

    settings = (api_key, base_url)
    if _CLIENT is not None and _CLIENT_SETTINGS == settings:
        return _CLIENT

    if base_url:
        _CLIENT = AsyncOpenAI(api_key=api_key, base_url=base_url)
    else:
        _CLIENT = AsyncOpenAI(api_key=api_key)
    _CLIENT_SETTINGS = settings
    return _CLIENT


def _strip_code_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\\s*", "", cleaned, count=1)
        cleaned = re.sub(r"\\s*```$", "", cleaned, count=1)
    return cleaned.strip()


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") == "text" and isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "\n".join(parts)
    return ""


def parse_json_object(raw_text: str) -> dict[str, Any]:
    cleaned = _strip_code_fences(raw_text)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise ValueError("LLM response did not contain a JSON object.") from None
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object.")

    return parsed


async def call_llm_json(prompt: str, *, temperature: float = 0.0, max_tokens: int = 1200) -> dict[str, Any]:
    if not (prompt or "").strip():
        raise ValueError("Prompt cannot be empty.")

    using_openai = bool(os.getenv("OPENAI_API_KEY"))
    api_key = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("NVIDIA_API_KEY")
    )
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY or NVIDIA_API_KEY for LLM call.")

    base_url = (
        (os.getenv("OPENAI_BASE_URL") if using_openai else None)
        or os.getenv("NVIDIA_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or (None if using_openai else "https://integrate.api.nvidia.com/v1")
    )
    model = (
        (os.getenv("OPENAI_MODEL") if using_openai else None)
        or os.getenv("NVIDIA_MODEL")
        or os.getenv("OPENAI_MODEL")
        or ("gpt-5.4-nano" if using_openai else "meta/llama-3.1-8b-instruct")
    )
    client = _get_client(api_key=api_key, base_url=base_url)

    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if not response.choices:
        raise ValueError("LLM returned no choices.")

    raw_content = _content_to_text(response.choices[0].message.content)
    if not raw_content:
        raise ValueError("LLM returned empty content.")

    return parse_json_object(raw_content)
