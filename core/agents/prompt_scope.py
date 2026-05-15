from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator


_ACTIVE_EXTRACTION_PROMPT: ContextVar[str] = ContextVar("orange_active_extraction_prompt", default="")


def active_extraction_prompt() -> str:
    return _ACTIVE_EXTRACTION_PROMPT.get()


@contextmanager
def scoped_extraction_prompt(prompt: str | None) -> Iterator[None]:
    token = _ACTIVE_EXTRACTION_PROMPT.set((prompt or "").strip())
    try:
        yield
    finally:
        _ACTIVE_EXTRACTION_PROMPT.reset(token)
