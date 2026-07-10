from __future__ import annotations

from datetime import date, datetime, time
import json
from typing import Any


def _serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_value(v) for v in value]
    if value.__class__.__module__.startswith("neo4j.time"):
        return str(value)
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _sanitize_properties(properties: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _serialize_value(value) for key, value in properties.items()}


def _run_query(driver: Any, query: str, **params: Any) -> list[Any]:
    if hasattr(driver, "run"):
        return list(driver.run(query, **params))
    if hasattr(driver, "session"):
        with driver.session() as session:
            return list(session.run(query, **params))
    raise ValueError("Neo4j driver must expose run(...) or session().")


def _record_get(record: Any, key: str, default: Any = None) -> Any:
    if record is None:
        return default
    if isinstance(record, dict):
        return record.get(key, default)
    try:
        return record.get(key, default)
    except Exception:  # noqa: BLE001
        try:
            return record[key]
        except Exception:  # noqa: BLE001
            return default


def _node_identity(node: Any) -> str:
    if node is None:
        return ""
    try:
        node_id = node.get("node_id")
        if node_id:
            return str(node_id)
    except Exception:  # noqa: BLE001
        pass
    try:
        return str(node.id)
    except Exception:  # noqa: BLE001
        return ""


def _edge_type(rel: Any) -> str:
    try:
        edge_type = getattr(rel, "type", "")
        return str(edge_type() if callable(edge_type) else edge_type)
    except Exception:  # noqa: BLE001
        return ""


def _edge_props(rel: Any) -> dict[str, Any]:
    try:
        return _sanitize_properties(dict(rel))
    except Exception:  # noqa: BLE001
        return {}


def _relationship_endpoints(rel: Any) -> tuple[str, str]:
    if rel is None:
        return "", ""
    start_node = getattr(rel, "start_node", None)
    end_node = getattr(rel, "end_node", None)
    if start_node is not None and end_node is not None:
        return _node_identity(start_node), _node_identity(end_node)
    try:
        nodes = list(getattr(rel, "nodes", []))
        if len(nodes) == 2:
            return _node_identity(nodes[0]), _node_identity(nodes[1])
    except Exception:  # noqa: BLE001
        pass
    return "", ""


def _neo4j_record_to_node(node: Any) -> dict[str, Any]:
    return {
        "id": _node_identity(node),
        "label": list(node.labels)[0] if getattr(node, "labels", None) else "Unknown",
        "properties": _sanitize_properties(dict(node)),
    }


def _add_node(nodes_by_id: dict[str, dict[str, Any]], node: Any) -> None:
    if node is None:
        return
    node_dict = _neo4j_record_to_node(node)
    node_id = node_dict.get("id")
    if not node_id:
        return
    existing = nodes_by_id.get(node_id)
    if existing is None:
        nodes_by_id[node_id] = node_dict
    else:
        existing["properties"].update(node_dict.get("properties", {}))


def _add_edge(edges: list[dict[str, Any]], seen_edges: set[tuple[str, str, str, str]], rel: Any) -> None:
    if rel is None:
        return
    source, target = _relationship_endpoints(rel)
    edge_type = _edge_type(rel)
    if not source or not target or not edge_type:
        return
    props = _edge_props(rel)
    key = (source, target, edge_type, json.dumps(props, sort_keys=True, default=str))
    if key in seen_edges:
        return
    seen_edges.add(key)
    edges.append({"source": source, "target": target, "type": edge_type, "properties": props})


def _empty_graph() -> dict[str, list[dict[str, Any]]]:
    return {"nodes": [], "edges": []}


def _without_raw_description(graph: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    for node in graph.get("nodes", []):
        properties = node.get("properties")
        if isinstance(properties, dict):
            properties.pop("raw_description", None)
    return graph


def _matches_scope(
    node: dict[str, Any],
    *,
    user_id: str | None = None,
    user_email: str | None = None,
    org_id: str | None = None,
    scope: str = "both",
) -> bool:
    properties = node.get("properties") if isinstance(node, dict) else None
    if not isinstance(properties, dict):
        return False

    requested_scope = scope if scope in {"user", "global", "both"} else "both"
    node_scope = str(properties.get("scope") or "").strip().lower()
    normalized_user_email = (user_email or "").strip().lower()
    normalized_user_id = (user_id or "").strip()
    normalized_org_id = (org_id or "").strip().lower()

    user_matches = False
    if normalized_user_email or normalized_user_id:
        user_matches = node_scope in {"", "user"} and (
            properties.get("user_email") == normalized_user_email
            or properties.get("user_id") == normalized_user_email
            or properties.get("user_id") == normalized_user_id
        )

    global_matches = (
        bool(normalized_org_id)
        and node_scope == "global"
        and str(properties.get("org_id") or "").strip().lower() == normalized_org_id
    )

    if requested_scope == "user":
        return user_matches
    if requested_scope == "global":
        return global_matches
    return user_matches or global_matches


def filter_graph_by_scope(
    graph: dict[str, list[dict[str, Any]]],
    *,
    user_id: str | None = None,
    user_email: str | None = None,
    org_id: str | None = None,
    scope: str = "both",
) -> dict[str, list[dict[str, Any]]]:
    visible_nodes = [
        node
        for node in graph.get("nodes", [])
        if _matches_scope(node, user_id=user_id, user_email=user_email, org_id=org_id, scope=scope)
    ]
    visible_ids = {str(node.get("id") or "") for node in visible_nodes}
    visible_edges = [
        edge
        for edge in graph.get("edges", [])
        if str(edge.get("source") or "") in visible_ids and str(edge.get("target") or "") in visible_ids
    ]
    return {"nodes": visible_nodes, "edges": visible_edges}


def _graph_from_rows(rows: list[Any]) -> dict[str, list[dict[str, Any]]]:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str, str]] = set()
    for row in rows:
        n = _record_get(row, "n")
        m = _record_get(row, "m")
        r = _record_get(row, "r")
        _add_node(nodes_by_id, n)
        _add_node(nodes_by_id, m)
        _add_edge(edges, seen_edges, r)
    return {"nodes": list(nodes_by_id.values()), "edges": edges}


def get_full_graph(
    driver: Any,
    user_id: str | None = None,
    *,
    scope: str = "both",
    user_email: str | None = None,
    org_id: str | None = None,
    include_raw: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    requested_scope = scope if scope in {"user", "global", "both"} else "both"
    normalized_user_email = (user_email or "").strip().lower() or None
    normalized_user_id = (user_id or "").strip() or None
    normalized_org_id = (org_id or "").strip().lower() or None
    if requested_scope in {"user", "both"} and not (normalized_user_email or normalized_user_id):
        if requested_scope == "user":
            return _empty_graph()
    if requested_scope in {"global", "both"} and not normalized_org_id:
        if requested_scope == "global":
            return _empty_graph()
    if not (normalized_user_email or normalized_user_id or normalized_org_id):
        return _empty_graph()

    query = """
    MATCH (n)
    WHERE
      (
        $scope IN ['user', 'both']
        AND n.scope = 'user'
        AND (
          ($user_email IS NOT NULL AND (n.user_email = $user_email OR n.user_id = $user_email))
          OR ($user_id IS NOT NULL AND n.user_id = $user_id)
        )
      )
      OR (
        $scope IN ['global', 'both']
        AND $org_id IS NOT NULL
        AND n.scope = 'global'
        AND n.org_id = $org_id
      )
    OPTIONAL MATCH (n)-[r]->(m)
    WHERE m IS NULL OR (
      (
        $scope IN ['user', 'both']
        AND m.scope = 'user'
        AND (
          ($user_email IS NOT NULL AND (m.user_email = $user_email OR m.user_id = $user_email))
          OR ($user_id IS NOT NULL AND m.user_id = $user_id)
        )
      )
      OR (
        $scope IN ['global', 'both']
        AND $org_id IS NOT NULL
        AND m.scope = 'global'
        AND m.org_id = $org_id
      )
    )
    RETURN n, r, m
    LIMIT 500
    """
    rows = _run_query(
        driver,
        query,
        scope=requested_scope,
        user_email=normalized_user_email,
        user_id=normalized_user_id,
        org_id=normalized_org_id,
    )
    graph = _graph_from_rows(rows)
    return graph if include_raw else _without_raw_description(graph)


def get_graph_version(
    driver: Any,
    user_id: str | None = None,
    *,
    scope: str = "both",
    user_email: str | None = None,
    org_id: str | None = None,
) -> dict[str, Any]:
    """Return a cheap scope-specific change token for live graph clients."""

    requested_scope = scope if scope in {"user", "global", "both"} else "both"
    normalized_user_email = (user_email or "").strip().lower() or None
    normalized_user_id = (user_id or "").strip() or None
    normalized_org_id = (org_id or "").strip().lower() or None
    if requested_scope == "user" and not (normalized_user_email or normalized_user_id):
        return {"version": "empty", "node_count": 0, "last_changed_at": None}
    if requested_scope == "global" and not normalized_org_id:
        return {"version": "empty", "node_count": 0, "last_changed_at": None}
    if not (normalized_user_email or normalized_user_id or normalized_org_id):
        return {"version": "empty", "node_count": 0, "last_changed_at": None}

    rows = _run_query(
        driver,
        """
        MATCH (n)
        WHERE
          (
            $scope IN ['user', 'both']
            AND n.scope = 'user'
            AND (
              ($user_email IS NOT NULL AND (n.user_email = $user_email OR n.user_id = $user_email))
              OR ($user_id IS NOT NULL AND n.user_id = $user_id)
            )
          )
          OR (
            $scope IN ['global', 'both']
            AND $org_id IS NOT NULL
            AND n.scope = 'global'
            AND n.org_id = $org_id
          )
        RETURN count(n) AS node_count,
               toString(max(coalesce(n.updated_at, n.created_at, n.ingested_at, n.started_at))) AS last_changed_at
        """,
        scope=requested_scope,
        user_email=normalized_user_email,
        user_id=normalized_user_id,
        org_id=normalized_org_id,
    )
    row = rows[0] if rows else {}
    node_count = int(_record_get(row, "node_count", 0) or 0)
    last_changed_at = _record_get(row, "last_changed_at")
    clean_changed_at = str(last_changed_at) if last_changed_at else None
    return {
        "version": f"{node_count}:{clean_changed_at or 'none'}",
        "node_count": node_count,
        "last_changed_at": clean_changed_at,
    }


def get_node_with_neighborhood(driver: Any, node_id: str) -> dict[str, list[dict[str, Any]]]:
    rows = _run_query(
        driver,
        """
        MATCH (n {node_id: $node_id})
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN n, r, m
        LIMIT 100
        """,
        node_id=node_id,
    )
    return _without_raw_description(_graph_from_rows(rows))


def get_all_sessions(driver: Any, user_id: str | None = None) -> list[dict[str, Any]]:
    rows = _run_query(
        driver,
        """
        MATCH (s:Session)
        WHERE $user_id IS NULL OR s.user_id = $user_id OR s.user_email = $user_id
        RETURN s.node_id AS node_id,
               s.title AS title,
               s.summary AS summary,
               s.source AS source,
               s.scope AS scope,
               s.started_at AS started_at,
               s.ended_at AS ended_at,
               s.message_count AS message_count
        ORDER BY s.started_at DESC
        LIMIT 100
        """,
        user_id=user_id,
    )
    return [_sanitize_properties(dict(row)) for row in rows]


def get_session_subgraph(driver: Any, session_id: str) -> dict[str, list[dict[str, Any]]]:
    rows = _run_query(
        driver,
        """
        MATCH (s:Session {node_id: $session_id})
        OPTIONAL MATCH (s)-[r]->(m)
        RETURN s AS n, r, m
        """,
        session_id=session_id,
    )
    return _without_raw_description(_graph_from_rows(rows))
