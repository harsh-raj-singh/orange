from __future__ import annotations

from core.storage.supabase_store import _scope, _slugify


def test_slugify_normalizes_external_ids() -> None:
    assert _slugify("Acme Platform Team") == "acme-platform-team"
    assert _slugify("  Org_123!!  ") == "org-123"
    assert _slugify("") == "default"


def test_scope_defaults_and_normalizes() -> None:
    assert _scope(None) == "user"
    assert _scope(" Global ") == "global"
