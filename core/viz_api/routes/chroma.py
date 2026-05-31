from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.graph_upsert.dedup import ORANGE_GLOBAL_VECTOR_COLLECTION, ORANGE_USER_VECTOR_COLLECTION
from core.viz_api.dependencies import get_chroma

router = APIRouter()


def _collection_name(scope: str) -> str:
    return ORANGE_GLOBAL_VECTOR_COLLECTION if scope == "global" else ORANGE_USER_VECTOR_COLLECTION


@router.get("/status")
async def chroma_status(scope: str = "user") -> JSONResponse:
    collection_name = _collection_name(scope)
    try:
        collection = get_chroma().get_collection(collection_name)
        return JSONResponse({"collection": collection_name, "count": collection.count()})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/peek")
async def chroma_peek(limit: int = 10, scope: str = "user") -> JSONResponse:
    collection_name = _collection_name(scope)
    try:
        collection = get_chroma().get_collection(collection_name)
        results = collection.peek(limit)
        embeddings = results.get("embeddings") if isinstance(results, dict) else None
        return JSONResponse(
            {
                "collection": collection_name,
                "ids": results.get("ids", []) if isinstance(results, dict) else [],
                "documents": results.get("documents", []) if isinstance(results, dict) else [],
                "embedding_dims": len(embeddings[0]) if embeddings else 0,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})
