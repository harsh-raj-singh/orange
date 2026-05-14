from __future__ import annotations

import pytest

from core.graph_schema_v2 import SourceType
from core.source_registry import get_source_config


def test_every_registered_source_returns_valid_config() -> None:
    for source in SourceType:
        config = get_source_config(source)
        assert config.retrieval_context_token_budget > 0
        assert len(config.extraction_agents) > 0


def test_unknown_source_raises_clearly() -> None:
    with pytest.raises(ValueError, match="Unknown source"):
        get_source_config("unknown_tool")  # type: ignore[arg-type]


def test_cursor_has_realtime_ping_slack_does_not() -> None:
    assert get_source_config(SourceType.CURSOR).realtime_ping_enabled is True
    assert get_source_config(SourceType.SLACK).realtime_ping_enabled is False


def test_resolve_callback_only_on_mcp_sources() -> None:
    assert get_source_config(SourceType.CURSOR).has_resolve_callback is True
    assert get_source_config(SourceType.SLACK).has_resolve_callback is False

