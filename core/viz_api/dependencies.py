from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_NEO4J_CLIENT: Any | None = None
_CHROMA_CLIENT: Any | None = None
_NEO4J_CONSTRAINTS_READY = False


def ensure_neo4j_constraints(neo4j: Any) -> None:
    global _NEO4J_CONSTRAINTS_READY
    if _NEO4J_CONSTRAINTS_READY:
        return

    statements = [
        "CREATE CONSTRAINT orange_problem_node_id IF NOT EXISTS FOR (p:Problem) REQUIRE p.node_id IS UNIQUE",
        "CREATE CONSTRAINT orange_solution_node_id IF NOT EXISTS FOR (s:Solution) REQUIRE s.node_id IS UNIQUE",
        "CREATE CONSTRAINT orange_session_node_id IF NOT EXISTS FOR (sess:Session) REQUIRE sess.node_id IS UNIQUE",
    ]
    try:
        if hasattr(neo4j, "run"):
            for statement in statements:
                neo4j.run(statement)
        elif hasattr(neo4j, "session"):
            with neo4j.session() as session:
                for statement in statements:
                    session.run(statement)
        _NEO4J_CONSTRAINTS_READY = True
    except Exception:
        # Some Neo4j-compatible backends do not support constraint DDL. Do not
        # block the demo API from starting; normal writes can still proceed.
        _NEO4J_CONSTRAINTS_READY = True


def get_neo4j() -> Any:
    global _NEO4J_CLIENT
    if _NEO4J_CLIENT is not None:
        return _NEO4J_CLIENT

    from neo4j import GraphDatabase

    url = os.getenv("MEMGRAPH_URL") or os.getenv("NEO4J_URL") or os.getenv("NEO4J_URI") or os.getenv("MEMGRAPH_BOLT_URL")
    if not url:
        host = os.getenv("MEMGRAPH_HOST")
        if host:
            port = os.getenv("MEMGRAPH_PORT", "7687")
            ssl_enabled = os.getenv("MEMGRAPH_SSL", "false").lower() in ("1", "true", "yes")
            scheme = os.getenv("MEMGRAPH_SCHEME") or ("bolt+ssc" if ssl_enabled else "bolt")
            url = f"{scheme}://{host}:{port}"

    if not url:
        raise ValueError("Missing MEMGRAPH_URL/NEO4J_URL (or MEMGRAPH_HOST) for MCP server.")

    username = os.getenv("MEMGRAPH_USERNAME") or os.getenv("NEO4J_USERNAME")
    password = os.getenv("MEMGRAPH_PASSWORD") or os.getenv("NEO4J_PASSWORD")

    if username and password:
        _NEO4J_CLIENT = GraphDatabase.driver(url, auth=(username, password))
    else:
        _NEO4J_CLIENT = GraphDatabase.driver(url)
    ensure_neo4j_constraints(_NEO4J_CLIENT)
    return _NEO4J_CLIENT


def get_chroma() -> Any:
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is not None:
        return _CHROMA_CLIENT

    import chromadb

    default_path = "/data/chroma" if os.getenv("RAILWAY_ENVIRONMENT") else "./chroma_db"
    chroma_path = os.getenv("CHROMA_PATH", default_path)
    _CHROMA_CLIENT = chromadb.PersistentClient(path=chroma_path)
    return _CHROMA_CLIENT
