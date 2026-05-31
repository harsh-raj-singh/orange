from __future__ import annotations

import os

from dotenv import load_dotenv
from neo4j import GraphDatabase


CONSTRAINTS = [
    """
    CREATE CONSTRAINT insight_node_scope_unique IF NOT EXISTS
    FOR (n:Insight) REQUIRE (n.node_id, n.scope) IS UNIQUE
    """,
    """
    CREATE CONSTRAINT session_node_scope_unique IF NOT EXISTS
    FOR (n:Session) REQUIRE (n.node_id, n.scope) IS UNIQUE
    """,
]


def _neo4j_url() -> str:
    url = os.getenv("NEO4J_URI") or os.getenv("NEO4J_URL") or os.getenv("MEMGRAPH_URL") or os.getenv("MEMGRAPH_BOLT_URL")
    if url:
        return url

    host = os.getenv("MEMGRAPH_HOST")
    if not host:
        raise RuntimeError("Set NEO4J_URI/NEO4J_URL/MEMGRAPH_URL or MEMGRAPH_HOST before applying constraints.")

    port = os.getenv("MEMGRAPH_PORT", "7687")
    ssl_enabled = os.getenv("MEMGRAPH_SSL", "false").lower() in {"1", "true", "yes"}
    scheme = os.getenv("MEMGRAPH_SCHEME") or ("bolt+ssc" if ssl_enabled else "bolt")
    return f"{scheme}://{host}:{port}"


def main() -> None:
    load_dotenv(override=True)
    username = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME") or os.getenv("MEMGRAPH_USERNAME")
    password = os.getenv("MEMGRAPH_PASSWORD") or os.getenv("NEO4J_PASSWORD")
    auth = (username, password) if username and password else None

    with GraphDatabase.driver(_neo4j_url(), auth=auth) as driver:
        with driver.session() as session:
            for constraint in CONSTRAINTS:
                session.run(constraint)

    print(f"Applied {len(CONSTRAINTS)} Neo4j scope constraints.")


if __name__ == "__main__":
    main()
