import json
import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv(override=True)

_CLIENT: AsyncOpenAI | None = None
_CLIENT_SETTINGS: tuple[str, str | None] | None = None
MAX_RETRIES = 3


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
            elif hasattr(item, "text") and isinstance(item.text, str):
                parts.append(item.text)
        return "\n".join(parts)
    return ""


def _strip_code_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, count=1)
        cleaned = re.sub(r"\s*```$", "", cleaned, count=1)
    return cleaned.strip()


def _resolve_llm_config() -> tuple[str, str, str | None]:
    api_key = (os.getenv("OPENAI_API_KEY") or os.getenv("NVIDIA_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY or NVIDIA_API_KEY.")

    using_openai = bool(os.getenv("OPENAI_API_KEY"))
    model = (
        (os.getenv("OPENAI_MODEL") if using_openai else None)
        or os.getenv("NVIDIA_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "gpt-5.4-nano"
    ).strip()
    base_url = (
        (os.getenv("OPENAI_BASE_URL") if using_openai else None)
        or os.getenv("NVIDIA_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
    )
    return api_key, model, base_url.strip() if isinstance(base_url, str) and base_url.strip() else None


async def call_llm_json(system_prompt: str, user_content: str) -> dict:
    caller_id = system_prompt[:40].replace("\n", " ")
    api_key, model, base_url = _resolve_llm_config()
    client = _get_client(api_key=api_key, base_url=base_url)

    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"[LLM] attempt={attempt} caller='{caller_id}' starting", flush=True)
        t0 = time.time()
        try:
            print(f"[LLM] attempt={attempt} sending request...", flush=True)
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3,
                max_tokens=4096,
            )

            if not response.choices:
                raise ValueError("LLM returned no choices.")

            raw_text = _content_to_text(response.choices[0].message.content)
            cleaned = _strip_code_fences(raw_text)
            result = json.loads(cleaned)
            print(
                f"[LLM] attempt={attempt} parsed ok total_wall={time.time()-t0:.1f}s",
                flush=True,
            )
            return result
        except json.JSONDecodeError as exc:
            print(
                f"[LLM] attempt={attempt} JSON PARSE ERROR after {time.time()-t0:.1f}s",
                flush=True,
            )
            raise ValueError(f"LLM returned invalid JSON on attempt {attempt}.\nRaw:\n{cleaned}") from exc
        except Exception as exc:  # noqa: BLE001
            print(f"[LLM] attempt={attempt} ERROR after {time.time()-t0:.1f}s: {exc}", flush=True)
            last_exc = exc
            if attempt == MAX_RETRIES:
                break

    raise TimeoutError(f"LLM call failed after {MAX_RETRIES} attempts. Last error: {last_exc}")
