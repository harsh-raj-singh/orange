from __future__ import annotations

from core.graph_schema_v2 import Insight


def build_insight_embed_string(insight: Insight) -> str:
    """Embed the durable learning, not just the graph card copy."""

    parts = [
        insight.what,
        insight.why or "",
        insight.how or "",
        insight.memory_kind,
        " ".join(insight.tags),
    ]
    return " ".join(part.strip() for part in parts if part and part.strip()).strip()
