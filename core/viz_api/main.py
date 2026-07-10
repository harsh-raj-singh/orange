from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.mcp_server.server import create_http_app as create_mcp_http_app, get_llm
from core.storage.worker import memory_worker_lifespan
from core.viz_api.dependencies import get_memory_repository
from core.viz_api.routes import demo, graph, health

mcp_app = create_mcp_http_app(path="/mcp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    repository = get_memory_repository()
    async with mcp_app.lifespan(app):
        worker_repository = (
            repository
            if os.getenv("ORANGE_MEMORY_WRITE_MODE", "inline").strip().lower() == "queued"
            else None
        )
        async with memory_worker_lifespan(worker_repository, llm_factory=get_llm):
            yield


app = FastAPI(title="Orange Graph & MCP API", version="2.0.0", lifespan=lifespan)


def _allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "")
    if raw.strip():
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return [
        "https://site-sage-eta-18.vercel.app",
        "http://localhost:3000",
        "http://localhost:3004",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(graph.router, prefix="/graph")
app.include_router(demo.router, prefix="/demo")
# FastAPI routes must be registered before the catch-all MCP application. This
# arrangement keeps OAuth discovery at the RFC-defined root paths while the
# protected MCP resource itself remains at /mcp.
app.mount("/", mcp_app)
