from __future__ import annotations

import importlib


def test_extraction_config_defaults(monkeypatch):
    monkeypatch.delenv("USE_DSPY_EXTRACTION", raising=False)
    monkeypatch.delenv("FALLBACK_TO_LEGACY", raising=False)
    monkeypatch.delenv("DUAL_WRITE_MODE", raising=False)
    module = importlib.import_module("core.memory_extraction.config")
    importlib.reload(module)

    cfg = module.ExtractionConfig()
    assert cfg.USE_DSPY_EXTRACTION is True
    assert cfg.FALLBACK_TO_LEGACY is True
    assert cfg.DUAL_WRITE_MODE is True


def test_extraction_config_env_override(monkeypatch):
    monkeypatch.setenv("USE_DSPY_EXTRACTION", "false")
    monkeypatch.setenv("FALLBACK_TO_LEGACY", "false")
    monkeypatch.setenv("DUAL_WRITE_MODE", "false")
    monkeypatch.setenv("MAX_EXTRACTION_RETRIES", "5")

    module = importlib.import_module("core.memory_extraction.config")
    importlib.reload(module)

    cfg = module.ExtractionConfig()
    assert cfg.USE_DSPY_EXTRACTION is False
    assert cfg.FALLBACK_TO_LEGACY is False
    assert cfg.DUAL_WRITE_MODE is False
    assert cfg.MAX_EXTRACTION_RETRIES == 5
