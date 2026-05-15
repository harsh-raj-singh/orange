from __future__ import annotations

import argparse
import os

import chromadb
from dotenv import load_dotenv
from neo4j import GraphDatabase

from core.graph_upsert.dedup import ORANGE_NODE_VECTOR_COLLECTION


def _resolve_neo4j_uri() -> str:
    explicit = (os.getenv("NEO4J_URL") or os.getenv("MEMGRAPH_URL") or os.getenv("MEMGRAPH_BOLT_URL") or "").strip()
    if explicit:
        return explicit

    host = (os.getenv("MEMGRAPH_HOST") or "").strip()
    if not host:
        raise ValueError("Missing NEO4J_URL/MEMGRAPH_URL or MEMGRAPH_HOST")

    scheme = (os.getenv("MEMGRAPH_SCHEME") or "bolt").strip()
    port = (os.getenv("MEMGRAPH_PORT") or "7687").strip()
    return f"{scheme}://{host}:{port}"


def _resolve_neo4j_auth() -> tuple[str, str] | None:
    username = (os.getenv("NEO4J_USERNAME") or os.getenv("MEMGRAPH_USERNAME") or "").strip()
    password = (os.getenv("NEO4J_PASSWORD") or os.getenv("MEMGRAPH_PASSWORD") or "").strip()
    if username and password:
        return username, password
    return None


def _fetch_neo4j_node_ids() -> set[str]:
    driver = GraphDatabase.driver(_resolve_neo4j_uri(), auth=_resolve_neo4j_auth(), connection_timeout=5)
    try:
        with driver.session() as session:
            rows = session.run("MATCH (n) WHERE n.node_id IS NOT NULL RETURN n.node_id AS node_id").data()
        return {str(row["node_id"]) for row in rows if row.get("node_id")}
    finally:
        driver.close()


def clean_orphans(*, apply: bool) -> dict[str, int]:
    chroma_path = os.getenv("CHROMA_PATH", "./chroma_db")
    chroma = chromadb.PersistentClient(path=chroma_path)
    collection = chroma.get_collection(ORANGE_NODE_VECTOR_COLLECTION)
    neo4j_node_ids = _fetch_neo4j_node_ids()
    payload = collection.get(include=["metadatas"])
    vector_ids = payload.get("ids", [])
    metadatas = payload.get("metadatas", [])

    orphan_ids: list[str] = []
    for vector_id, metadata in zip(vector_ids, metadatas):
        neo4j_node_id = str((metadata or {}).get("neo4j_node_id") or "").strip()
        if not neo4j_node_id or neo4j_node_id not in neo4j_node_ids:
            orphan_ids.append(str(vector_id))

    if apply and orphan_ids:
        collection.delete(ids=orphan_ids)

    return {
        "neo4j_nodes": len(neo4j_node_ids),
        "chroma_before": len(vector_ids),
        "orphan_vectors": len(orphan_ids),
        "chroma_after": collection.count(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove Chroma vectors whose Neo4j node no longer exists.")
    parser.add_argument("--apply", action="store_true", help="Actually delete orphan vectors. Defaults to dry-run.")
    args = parser.parse_args()

    load_dotenv()
    stats = clean_orphans(apply=args.apply)
    mode = "apply" if args.apply else "dry_run"
    print(f"mode={mode}")
    for key, value in stats.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
