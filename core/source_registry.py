from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.graph_schema_v2 import SourceType


class ConversationType(str, Enum):
    DEBUGGING = "debugging"
    BRAINSTORM = "brainstorm"
    QA = "qa"
    DECISION = "decision"
    CASUAL = "casual"


@dataclass(frozen=True)
class SourceConfig:
    source_id: SourceType

    # Which conversation types are realistic for this source.
    # Classifier is still the authority — this is just a hint/filter.
    expected_conversation_types: tuple[ConversationType, ...]

    # Whether this source supports mid-session lightweight context pinging.
    # Only True for MCP-based sources where we control the client.
    realtime_ping_enabled: bool

    # Whether this source can send an explicit resolve() callback.
    has_resolve_callback: bool

    # How many tokens of context to inject into the session prompt.
    # Cursor gets more (it's a focused technical session).
    # Slack gets less (replies need to be concise).
    retrieval_context_token_budget: int

    # Extraction agents to run post-session, in order of priority.
    # Classifier always runs first regardless — this is what runs after.
    extraction_agents: tuple[str, ...]


SOURCE_REGISTRY: dict[SourceType, SourceConfig] = {
    SourceType.CURSOR: SourceConfig(
        source_id=SourceType.CURSOR,
        expected_conversation_types=(
            ConversationType.DEBUGGING,
            ConversationType.QA,
        ),
        realtime_ping_enabled=True,
        has_resolve_callback=True,
        retrieval_context_token_budget=2000,
        extraction_agents=("DebugExtractionAgent", "ConceptExtractionAgent"),
    ),
    SourceType.SLACK: SourceConfig(
        source_id=SourceType.SLACK,
        expected_conversation_types=(
            ConversationType.BRAINSTORM,
            ConversationType.DECISION,
            ConversationType.QA,
            ConversationType.CASUAL,
        ),
        realtime_ping_enabled=False,
        has_resolve_callback=False,
        retrieval_context_token_budget=800,
        extraction_agents=("BrainstormExtractionAgent", "ConceptExtractionAgent"),
    ),
    SourceType.GMAIL: SourceConfig(
        source_id=SourceType.GMAIL,
        expected_conversation_types=(
            ConversationType.DECISION,
            ConversationType.QA,
        ),
        realtime_ping_enabled=False,
        has_resolve_callback=False,
        retrieval_context_token_budget=1000,
        extraction_agents=("ConceptExtractionAgent",),  # placeholder until Gmail agent exists
    ),
    SourceType.STREAMLIT: SourceConfig(
        source_id=SourceType.STREAMLIT,
        expected_conversation_types=(
            ConversationType.DEBUGGING,
            ConversationType.BRAINSTORM,
            ConversationType.QA,
            ConversationType.DECISION,
        ),
        realtime_ping_enabled=False,
        has_resolve_callback=False,
        retrieval_context_token_budget=1500,
        extraction_agents=("DebugExtractionAgent", "BrainstormExtractionAgent", "ConceptExtractionAgent"),
    ),
}


def get_source_config(source: SourceType) -> SourceConfig:
    """Single lookup point. Raises clearly if source is unknown."""
    if source not in SOURCE_REGISTRY:
        raise ValueError(f"Unknown source: {source!r}. Register it in SOURCE_REGISTRY first.")
    return SOURCE_REGISTRY[source]

