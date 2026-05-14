from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class MergeDecision:
    """Decision produced by problem deduplication before write."""

    action: Literal["MERGE", "CREATE"]
    existing_node_id: str | None
    similarity_score: float | None
    arbitration_used: bool
