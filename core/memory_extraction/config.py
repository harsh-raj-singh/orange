from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ExtractionConfig:
    """Configuration for memory extraction system."""

    USE_DSPY_EXTRACTION: bool = _env_bool("USE_DSPY_EXTRACTION", True)
    FALLBACK_TO_LEGACY: bool = _env_bool("FALLBACK_TO_LEGACY", True)
    DUAL_WRITE_MODE: bool = _env_bool("DUAL_WRITE_MODE", True)

    MIN_CONFIDENCE_FOR_STORAGE: float = float(os.getenv("MIN_CONFIDENCE", "0.3"))
    MIN_IMPORTANCE_FOR_GRAPH: float = float(os.getenv("MIN_IMPORTANCE_GRAPH", "0.6"))
    RETRIEVAL_THRESHOLD: float = float(os.getenv("RETRIEVAL_THRESHOLD", "0.75"))

    MAX_EXTRACTION_RETRIES: int = int(os.getenv("MAX_EXTRACTION_RETRIES", "2"))
    EXTRACTION_TIMEOUT_SECONDS: int = int(os.getenv("EXTRACTION_TIMEOUT", "60"))

    EXTRACTION_VERSION: str = os.getenv("EXTRACTION_VERSION", "dspy_v1")
