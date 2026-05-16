from __future__ import annotations

from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.viz_api.dependencies import get_chroma

router = APIRouter()
_EMBED_FN = DefaultEmbeddingFunction()
_COLLECTION = "orange_node_vectors"


@router.get("/status")
async def chroma_status() -> JSONResponse:
    try:
        collection = get_chroma().get_collection(_COLLECTION)
        return JSONResponse({"collection": _COLLECTION, "count": collection.count()})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/peek")
async def chroma_peek(limit: int = 10) -> JSONResponse:
    try:
        collection = get_chroma().get_collection(_COLLECTION)
        results = collection.peek(limit)
        embeddings = results.get("embeddings") if isinstance(results, dict) else None
        return JSONResponse(
            {
                "ids": results.get("ids", []) if isinstance(results, dict) else [],
                "documents": results.get("documents", []) if isinstance(results, dict) else [],
                "embedding_dims": len(embeddings[0]) if embeddings else 0,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/search")
async def chroma_search(query: str, user_id: str | None = None, limit: int = 5) -> JSONResponse:
    try:
        collection = get_chroma().get_collection(_COLLECTION)
        query_embeddings = _EMBED_FN([query])
        query_kwargs = {"query_embeddings": query_embeddings, "n_results": limit}
        if user_id:
            query_kwargs["where"] = {"user_id": user_id}
        results = collection.query(**query_kwargs)
        return JSONResponse(
            {
                "ids": results.get("ids", []) if isinstance(results, dict) else [],
                "documents": results.get("documents", []) if isinstance(results, dict) else [],
                "metadatas": results.get("metadatas", []) if isinstance(results, dict) else [],
                "distances": results.get("distances", []) if isinstance(results, dict) else [],
            }
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})
