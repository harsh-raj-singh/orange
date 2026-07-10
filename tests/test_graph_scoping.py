from __future__ import annotations

from core.graph_queries.neo4j_queries import filter_graph_by_scope, get_graph_version


def _graph_fixture() -> dict:
    return {
        "nodes": [
            {
                "id": "user-node",
                "properties": {
                    "scope": "user",
                    "user_email": "dev@example.com",
                    "user_id": "dev@example.com",
                },
            },
            {
                "id": "global-node",
                "properties": {
                    "scope": "global",
                    "org_id": "acme",
                },
            },
        ],
        "edges": [
            {"source": "user-node", "target": "global-node", "type": "RELATED_TO"},
        ],
    }


def test_filter_graph_by_scope_rejects_user_scope_without_identity() -> None:
    graph = filter_graph_by_scope(_graph_fixture(), scope="user")

    assert graph == {"nodes": [], "edges": []}


def test_filter_graph_by_scope_keeps_only_global_nodes_without_user_identity() -> None:
    graph = filter_graph_by_scope(_graph_fixture(), scope="both", org_id="acme")

    assert [node["id"] for node in graph["nodes"]] == ["global-node"]
    assert graph["edges"] == []


def test_filter_graph_by_scope_keeps_matching_user_and_global_nodes() -> None:
    graph = filter_graph_by_scope(
        _graph_fixture(),
        scope="both",
        user_email="dev@example.com",
        user_id="dev@example.com",
        org_id="acme",
    )

    assert {node["id"] for node in graph["nodes"]} == {"user-node", "global-node"}
    assert len(graph["edges"]) == 1


def test_get_graph_version_returns_scoped_change_token() -> None:
    class VersionDriver:
        def __init__(self) -> None:
            self.params = {}

        def run(self, _query: str, **params):
            self.params = params
            return [{"node_count": 4, "last_changed_at": "2026-07-10T12:00:00Z"}]

    driver = VersionDriver()

    result = get_graph_version(
        driver,
        user_email="DEV@example.com",
        org_id="acme",
        scope="both",
    )

    assert result == {
        "version": "4:2026-07-10T12:00:00Z",
        "node_count": 4,
        "last_changed_at": "2026-07-10T12:00:00Z",
    }
    assert driver.params == {
        "scope": "both",
        "user_email": "dev@example.com",
        "user_id": None,
        "org_id": "acme",
    }


def test_get_graph_version_skips_query_without_scope_identity() -> None:
    class FailDriver:
        def run(self, _query: str, **_params):
            raise AssertionError("query should not run")

    assert get_graph_version(FailDriver(), scope="both") == {
        "version": "empty",
        "node_count": 0,
        "last_changed_at": None,
    }
