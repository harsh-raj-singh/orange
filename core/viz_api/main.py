from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.viz_api.routes import chroma, demo, graph, health

app = FastAPI(title="Orange1 Graph Viz API", version="1.0.0")


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
app.include_router(chroma.router, prefix="/chroma")
app.include_router(demo.router, prefix="/demo")
