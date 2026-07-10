from __future__ import annotations

from dataclasses import dataclass

from core.graph_schema_v2 import SourceType


@dataclass(frozen=True)
class SourceConfig:
    source_id: SourceType
    realtime_ping_enabled: bool
    retrieval_context_token_budget: int


SOURCE_REGISTRY: dict[SourceType, SourceConfig] = {
    SourceType.MCP: SourceConfig(SourceType.MCP, realtime_ping_enabled=True, retrieval_context_token_budget=1800),
    SourceType.CODEX: SourceConfig(SourceType.CODEX, realtime_ping_enabled=True, retrieval_context_token_budget=1800),
    SourceType.CURSOR: SourceConfig(SourceType.CURSOR, realtime_ping_enabled=True, retrieval_context_token_budget=2000),
    SourceType.CLAUDE: SourceConfig(SourceType.CLAUDE, realtime_ping_enabled=True, retrieval_context_token_budget=1800),
    SourceType.SLACK: SourceConfig(SourceType.SLACK, realtime_ping_enabled=False, retrieval_context_token_budget=800),
    SourceType.GMAIL: SourceConfig(SourceType.GMAIL, realtime_ping_enabled=False, retrieval_context_token_budget=1000),
}


def get_source_config(source: SourceType) -> SourceConfig:
    """Single lookup point for supported ingestion sources."""

    if source not in SOURCE_REGISTRY:
        raise ValueError(f"Unknown source: {source!r}. Register it in SOURCE_REGISTRY first.")
    return SOURCE_REGISTRY[source]
