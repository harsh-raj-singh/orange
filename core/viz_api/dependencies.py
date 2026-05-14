from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_NEO4J_CLIENT: Any | None = None
_CHROMA_CLIENT: Any | None = None


def get_neo4j() -> Any:
    global _NEO4J_CLIENT
    if _NEO4J_CLIENT is not None:
        return _NEO4J_CLIENT

    from neo4j import GraphDatabase

    url = os.getenv("MEMGRAPH_URL") or os.getenv("NEO4J_URL") or os.getenv("MEMGRAPH_BOLT_URL")
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
    return _NEO4J_CLIENT


def get_chroma() -> Any:
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is not None:
        return _CHROMA_CLIENT

    import chromadb

    chroma_path = os.getenv("CHROMA_PATH", "./chroma_db")
    _CHROMA_CLIENT = chromadb.PersistentClient(path=chroma_path)
    return _CHROMA_CLIENT
