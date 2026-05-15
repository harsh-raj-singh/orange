from __future__ import annotations

from core.storage.supabase_store import _slugify


def test_slugify_normalizes_external_ids() -> None:
    assert _slugify("Acme Platform Team") == "acme-platform-team"
    assert _slugify("  Org_123!!  ") == "org-123"
    assert _slugify("") == "default"
