from __future__ import annotations

from core.graph_queries.neo4j_queries import filter_graph_by_scope


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
