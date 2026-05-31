from __future__ import annotations

from typing import Any

from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

ORANGE_USER_VECTOR_COLLECTION = "orange_user_vectors"
ORANGE_GLOBAL_VECTOR_COLLECTION = "orange_global_vectors"
ORANGE_NODE_VECTOR_COLLECTION = ORANGE_USER_VECTOR_COLLECTION
_EMBED_FN = DefaultEmbeddingFunction()


class _FallbackCollection:
    def query(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"ids": [[]], "distances": [[]], "metadatas": [[]]}


def get_or_create_orange_collection(chroma: Any, *, scope: str = "user") -> Any:
    """Resolve the scoped Orange vector collection, creating it when supported."""

    if chroma is None:
        return _FallbackCollection()
    if callable(getattr(chroma, "query", None)):
        return chroma

    collection_name = (
        ORANGE_GLOBAL_VECTOR_COLLECTION
        if str(scope or "user").strip().lower() == "global"
        else ORANGE_USER_VECTOR_COLLECTION
    )
    if callable(getattr(chroma, "get_or_create_collection", None)):
        return chroma.get_or_create_collection(
            collection_name,
            embedding_function=_EMBED_FN,
            metadata={"hnsw:space": "cosine"},
        )
    if callable(getattr(chroma, "get_collection", None)):
        return chroma.get_collection(collection_name)
    return chroma


def get_or_create_user_collection(chroma: Any) -> Any:
    return get_or_create_orange_collection(chroma, scope="user")


def get_or_create_global_collection(chroma: Any) -> Any:
    return get_or_create_orange_collection(chroma, scope="global")
