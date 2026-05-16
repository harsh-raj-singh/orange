"""Backfill vector payload fields from legacy summary keys."""

from __future__ import annotations

from core.complete_chat_system import ChatCentricMemorySystem


def run(system: ChatCentricMemorySystem, user_id: str, limit: int = 1000) -> int:
    updated = 0
    hits = system.vector_store.list(filters={"user_id": user_id}, limit=limit)
    for hit in hits:
        payload = hit.payload if hasattr(hit, "payload") else {}
        if not payload:
            continue

        changed = False
        if not payload.get("search_query_intent") and payload.get("query_summary"):
            payload["search_query_intent"] = payload.get("query_summary")
            changed = True
        if not payload.get("search_solution_summary") and payload.get("response_summary"):
            payload["search_solution_summary"] = payload.get("response_summary")
            changed = True
        if not payload.get("search_keywords") and payload.get("tags"):
            payload["search_keywords"] = payload.get("tags")
            changed = True

        if not changed:
            continue

        vector = getattr(hit, "vector", None)
        if vector is not None:
            system.vector_store.update(hit.id, vector=vector, payload=payload)
        else:
            system.vector_store.update(hit.id, payload=payload)
        updated += 1

    return updated


if __name__ == "__main__":
    raise SystemExit("Use run(system, user_id) from an initialized runtime context.")
