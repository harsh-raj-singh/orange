from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.viz_api.routes import chroma, graph, health

app = FastAPI(title="Orange1 Graph Viz API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(graph.router, prefix="/graph")
app.include_router(chroma.router, prefix="/chroma")
