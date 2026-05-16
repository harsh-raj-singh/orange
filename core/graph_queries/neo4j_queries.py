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

    # Neo4j temporal values are not JSON serializable; render as ISO-like string.
    if value.__class__.__module__.startswith("neo4j.time"):
        return str(value)

    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _sanitize_properties(properties: dict[str, Any]) -> dict[str, Any]:
    return {str(k): _serialize_value(v) for k, v in properties.items()}


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


def _relationship_endpoints(rel: Any) -> tuple[str, str]:
    if rel is None:
        return "", ""
    try:
        start_node = getattr(rel, "start_node", None)
        end_node = getattr(rel, "end_node", None)
        if start_node is not None and end_node is not None:
            return _node_identity(start_node), _node_identity(end_node)
    except Exception:  # noqa: BLE001
        pass

    try:
        nodes = list(getattr(rel, "nodes", []))
        if len(nodes) == 2:
            return _node_identity(nodes[0]), _node_identity(nodes[1])
    except Exception:  # noqa: BLE001
        pass

    return "", ""


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
        return
    # Merge additional properties from later observations.
    existing["properties"].update(node_dict.get("properties", {}))


def _add_edge(
    edges: list[dict[str, Any]],
    seen_edges: set[tuple[str, str, str, str]],
    edge: dict[str, Any],
) -> None:
    source = str(edge.get("source") or "")
    target = str(edge.get("target") or "")
    edge_type = str(edge.get("type") or "")
    if not source or not target or not edge_type:
        return
    props = _sanitize_properties(edge.get("properties", {}))
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


def _neo4j_record_to_node(node) -> dict:
    """Convert a neo4j Node object to serializable dict."""
    return {
        "id": node.get("node_id", str(node.id)),
        "label": list(node.labels)[0] if node.labels else "Unknown",
        "properties": _sanitize_properties(dict(node)),
    }


def _neo4j_record_to_edge(rel, source_id: str, target_id: str) -> dict:
    """Convert a neo4j Relationship object to serializable dict."""
    return {
        "source": source_id,
        "target": target_id,
        "type": rel.type,
        "properties": _sanitize_properties(dict(rel)),
    }


def get_full_graph(
    driver,
    user_id: str | None = None,
    *,
    scope: str = "both",
    user_email: str | None = None,
    org_id: str | None = None,
    include_raw: bool = False,
) -> dict:
    """
    Returns all nodes + all edges in {nodes: [...], edges: [...]} format.
    If user_id provided, filter nodes by user_id property.
    """
    query = """
    MATCH (n)
    WHERE
      (
        $scope = 'both'
        AND (
          ($org_id IS NOT NULL AND n.scope = 'global' AND n.org_id = $org_id)
          OR (
            n.scope = 'user'
            AND (
              $user_email IS NULL
              OR n.user_email = $user_email
              OR n.user_id = $user_email
              OR n.user_id = $user_id
            )
          )
        )
      )
      OR ($scope = 'global' AND $org_id IS NOT NULL AND n.scope = 'global' AND n.org_id = $org_id)
      OR (
        $scope = 'user'
        AND (
          n.scope = 'user'
          OR n.scope IS NULL
        )
        AND (
          $user_email IS NULL
          OR n.user_email = $user_email
          OR n.user_id = $user_email
          OR n.user_id = $user_id
        )
      )
    OPTIONAL MATCH (n)-[r]->(m)
    WHERE m IS NULL OR (
      (
        $scope = 'both'
        AND (
          ($org_id IS NOT NULL AND m.scope = 'global' AND m.org_id = $org_id)
          OR (
            m.scope = 'user'
            AND (
              $user_email IS NULL
              OR m.user_email = $user_email
              OR m.user_id = $user_email
              OR m.user_id = $user_id
            )
          )
        )
      )
      OR ($scope = 'global' AND $org_id IS NOT NULL AND m.scope = 'global' AND m.org_id = $org_id)
      OR (
        $scope = 'user'
        AND (
          m.scope = 'user'
          OR m.scope IS NULL
        )
        AND (
          $user_email IS NULL
          OR m.user_email = $user_email
          OR m.user_id = $user_email
          OR m.user_id = $user_id
        )
      )
    )
    RETURN n, r, m
    """

    records = _run_query(
        driver,
        query,
        user_id=user_id,
        user_email=user_email,
        org_id=org_id,
        scope=scope if scope in {"user", "global", "both"} else "both",
    )
    nodes_by_id: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str, str]] = set()

    for record in records:
        n = _record_get(record, "n")
        r = _record_get(record, "r")
        m = _record_get(record, "m")
        _add_node(nodes_by_id, n)
        _add_node(nodes_by_id, m)

        if n is None or r is None or m is None:
            continue
        source_id = _node_identity(n)
        target_id = _node_identity(m)
        if not source_id or not target_id:
            continue
        edge = _neo4j_record_to_edge(r, source_id=source_id, target_id=target_id)
        _add_edge(edges, seen_edges, edge)

    graph = {"nodes": list(nodes_by_id.values()), "edges": edges}
    return graph if include_raw else _without_raw_description(graph)


def get_node_with_neighborhood(driver, node_id: str) -> dict:
    """
    Returns single node + all 1-hop neighbors + all edges between them.
    Reuses type-specific fetch logic for Problem/Solution node enrichment.
    """
    label_records = _run_query(
        driver,
        """
        MATCH (n {node_id: $node_id})
        RETURN n, labels(n) AS labels
        LIMIT 1
        """,
        node_id=node_id,
    )
    if not label_records:
        return _empty_graph()

    root_record = label_records[0]
    root_node = _record_get(root_record, "n")
    if root_node is None:
        return _empty_graph()

    labels = _record_get(root_record, "labels", []) or []
    node_label = labels[0] if labels else "Unknown"

    nodes_by_id: dict[str, dict[str, Any]] = {}
    _add_node(nodes_by_id, root_node)
    root_id = _node_identity(root_node)

    if node_label in {"Problem", "Solution"}:
        from core.mcp_server.handlers import _fetch_problem_node, _fetch_solution_node

        details = _fetch_problem_node(driver, node_id) if node_label == "Problem" else _fetch_solution_node(driver, node_id)
        if details and root_id in nodes_by_id:
            nodes_by_id[root_id]["properties"].update(_sanitize_properties(details))

    generic_records = _run_query(
        driver,
        """
        MATCH (n {node_id: $node_id})
        OPTIONAL MATCH (n)-[r]->(neighbor)
        OPTIONAL MATCH (n)<-[r2]-(neighbor2)
        RETURN n, collect(r) as out_edges, collect(neighbor) as out_neighbors,
               collect(r2) as in_edges, collect(neighbor2) as in_neighbors
        """,
        node_id=node_id,
    )
    if not generic_records:
        return {"nodes": list(nodes_by_id.values()), "edges": []}

    record = generic_records[0]
    out_neighbors = _record_get(record, "out_neighbors", []) or []
    in_neighbors = _record_get(record, "in_neighbors", []) or []
    out_edges = _record_get(record, "out_edges", []) or []
    in_edges = _record_get(record, "in_edges", []) or []

    for neighbor in list(out_neighbors) + list(in_neighbors):
        _add_node(nodes_by_id, neighbor)

    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str, str]] = set()
    for rel in list(out_edges) + list(in_edges):
        if rel is None:
            continue
        source_id, target_id = _relationship_endpoints(rel)
        if not source_id or not target_id:
            continue
        edge = {
            "source": source_id,
            "target": target_id,
            "type": _edge_type(rel),
            "properties": _edge_props(rel),
        }
        _add_edge(edges, seen_edges, edge)

    return {"nodes": list(nodes_by_id.values()), "edges": edges}


def get_all_sessions(driver, user_id: str | None = None) -> list:
    """
    Returns all Session nodes sorted by created_at descending.
    """
    records = _run_query(
        driver,
        """
        MATCH (s:Session)
        WHERE $user_id IS NULL OR s.user_id = $user_id
        RETURN s ORDER BY s.created_at DESC
        """,
        user_id=user_id,
    )
    return [_neo4j_record_to_node(_record_get(record, "s")) for record in records if _record_get(record, "s") is not None]


def get_session_subgraph(driver, session_id: str) -> dict:
    """
    Returns full subgraph for one session — the session node + everything
    reachable from it within 3 hops.
    """
    records = _run_query(
        driver,
        """
        MATCH (s:Session {node_id: $session_id})
        OPTIONAL MATCH path = (s)-[*1..3]->(n)
        RETURN s, relationships(path) as rels, nodes(path) as path_nodes
        """,
        session_id=session_id,
    )
    if not records:
        return _empty_graph()

    nodes_by_id: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str, str]] = set()

    for record in records:
        session_node = _record_get(record, "s")
        _add_node(nodes_by_id, session_node)

        for node in _record_get(record, "path_nodes", []) or []:
            _add_node(nodes_by_id, node)

        for rel in _record_get(record, "rels", []) or []:
            source_id, target_id = _relationship_endpoints(rel)
            if not source_id or not target_id:
                continue
            edge = {
                "source": source_id,
                "target": target_id,
                "type": _edge_type(rel),
                "properties": _edge_props(rel),
            }
            _add_edge(edges, seen_edges, edge)

    return {"nodes": list(nodes_by_id.values()), "edges": edges}


def get_all_problems(driver, user_id: str | None = None) -> list:
    """
    Returns all Problem nodes with their recurrence_count and depth.
    """
    records = _run_query(
        driver,
        """
        MATCH (p:Problem)
        WHERE $user_id IS NULL OR p.user_id = $user_id
        RETURN p ORDER BY p.recurrence_count DESC
        """,
        user_id=user_id,
    )
    return [_neo4j_record_to_node(_record_get(record, "p")) for record in records if _record_get(record, "p") is not None]


def get_problem_chain(driver, canonical_label: str, user_id: str) -> dict:
    """
    Returns a problem + all its solutions + RECURS_AS edges + CAUSED_BY chain.
    """
    records = _run_query(
        driver,
        """
        MATCH (p:Problem {canonical_label: $canonical_label, user_id: $user_id})
        OPTIONAL MATCH (p)-[:ATTEMPTED_BY]->(s:Solution)
        OPTIONAL MATCH (p)-[:RESOLVED_BY]->(rs:Solution)
        OPTIONAL MATCH (p)-[:CAUSED_BY]->(parent:Problem)
        OPTIONAL MATCH (child:Problem)-[:CAUSED_BY]->(p)
        OPTIONAL MATCH (session:Session)-[:RECURS_AS]->(p)
        RETURN p, collect(DISTINCT s) as solutions, rs,
               parent, collect(DISTINCT child) as children,
               collect(DISTINCT session) as sessions
        """,
        canonical_label=canonical_label,
        user_id=user_id,
    )
    if not records:
        return _empty_graph()

    row = records[0]
    problem = _record_get(row, "p")
    if problem is None:
        return _empty_graph()

    nodes_by_id: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str, str]] = set()

    _add_node(nodes_by_id, problem)
    problem_id = _node_identity(problem)

    for solution in _record_get(row, "solutions", []) or []:
        if solution is None:
            continue
        _add_node(nodes_by_id, solution)
        _add_edge(edges, seen_edges, {"source": problem_id, "target": _node_identity(solution), "type": "ATTEMPTED_BY", "properties": {}})

    resolved = _record_get(row, "rs")
    if resolved is not None:
        _add_node(nodes_by_id, resolved)
        _add_edge(edges, seen_edges, {"source": problem_id, "target": _node_identity(resolved), "type": "RESOLVED_BY", "properties": {}})

    parent = _record_get(row, "parent")
    if parent is not None:
        _add_node(nodes_by_id, parent)
        _add_edge(edges, seen_edges, {"source": problem_id, "target": _node_identity(parent), "type": "CAUSED_BY", "properties": {}})

    for child in _record_get(row, "children", []) or []:
        if child is None:
            continue
        _add_node(nodes_by_id, child)
        _add_edge(edges, seen_edges, {"source": _node_identity(child), "target": problem_id, "type": "CAUSED_BY", "properties": {}})

    for session in _record_get(row, "sessions", []) or []:
        if session is None:
            continue
        _add_node(nodes_by_id, session)
        _add_edge(edges, seen_edges, {"source": _node_identity(session), "target": problem_id, "type": "RECURS_AS", "properties": {}})

    return {"nodes": list(nodes_by_id.values()), "edges": edges}


def get_relationship_stats(driver) -> list:
    """
    Returns all relationship types with counts.
    """
    records = _run_query(
        driver,
        """
        MATCH ()-[r]->()
        RETURN type(r) as relationship_type, count(r) as count
        ORDER BY count DESC
        """
    )
    return [
        {
            "relationship_type": _serialize_value(_record_get(record, "relationship_type")),
            "count": _serialize_value(_record_get(record, "count")),
        }
        for record in records
    ]


def get_nodes_since(driver, since_timestamp: float, user_id: str | None = None) -> dict:
    """
    Returns all nodes created after a unix timestamp. Used for polling.
    """
    records = _run_query(
        driver,
        """
        MATCH (n)
        WHERE n.created_at > datetime({epochSeconds: toInteger($since)})
        AND ($user_id IS NULL OR n.user_id = $user_id)
        OPTIONAL MATCH (n)-[r]->(m)
        WHERE m.created_at > datetime({epochSeconds: toInteger($since)})
        RETURN n, r, m
        """,
        since=since_timestamp,
        user_id=user_id,
    )

    nodes_by_id: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str, str]] = set()

    for record in records:
        n = _record_get(record, "n")
        r = _record_get(record, "r")
        m = _record_get(record, "m")
        _add_node(nodes_by_id, n)
        _add_node(nodes_by_id, m)
        if n is None or r is None or m is None:
            continue
        source_id = _node_identity(n)
        target_id = _node_identity(m)
        if not source_id or not target_id:
            continue
        edge = _neo4j_record_to_edge(r, source_id=source_id, target_id=target_id)
        _add_edge(edges, seen_edges, edge)

    return {"nodes": list(nodes_by_id.values()), "edges": edges}
