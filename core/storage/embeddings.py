from __future__ import annotations

import logging
import os
import time
from typing import Protocol

from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536


class EmbeddingProvider(Protocol):
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingProvider:
    """Small synchronous adapter used inside the Postgres writer thread."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
        base_url: str | None = None,
    ) -> None:
        resolved_key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        if not resolved_key:
            raise RuntimeError("OPENAI_API_KEY is required for Postgres vector memory.")
        self.model = (model or os.getenv("OPENAI_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL).strip()
        self.dimensions = dimensions
        resolved_base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "").strip() or None
        self.client = OpenAI(api_key=resolved_key, base_url=resolved_base_url)

    def embed(self, texts: list[str]) -> list[list[float]]:
        cleaned = [str(text or "").strip() for text in texts]
        if not cleaned or any(not text for text in cleaned):
            raise ValueError("Embedding inputs must be non-empty strings.")

        started = time.monotonic()
        response = self.client.embeddings.create(model=self.model, input=cleaned)
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in ordered]
        if len(vectors) != len(cleaned):
            raise RuntimeError("Embedding provider returned an unexpected result count.")
        if any(len(vector) != self.dimensions for vector in vectors):
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {self.dimensions} for {self.model}."
            )
        logger.info(
            "embedding_batch_succeeded",
            extra={
                "model": self.model,
                "input_count": len(cleaned),
                "duration_seconds": round(time.monotonic() - started, 3),
            },
        )
        return vectors


def vector_literal(vector: list[float]) -> str:
    """Return pgvector's text input representation without another dependency."""

    if not vector:
        raise ValueError("vector must not be empty")
    return "[" + ",".join(format(float(value), ".10g") for value in vector) + "]"
