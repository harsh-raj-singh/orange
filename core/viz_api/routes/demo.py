from __future__ import annotations

import hashlib
from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.mcp_server.handlers import handle_ping_context, handle_store_session
from core.mcp_server.models import PingContextRequest, StoreSessionRequest
from core.viz_api.dependencies import get_chroma, get_neo4j

router = APIRouter()


class DemoProfile(BaseModel):
    name: str | None = None
    email: str | None = None
    role: str | None = None
    company: str | None = None
    teamProject: str | None = None


class DemoMessage(BaseModel):
    role: str
    content: str


class DemoCompletePayload(BaseModel):
    profile: DemoProfile | None = None
    messages: list[DemoMessage] = Field(default_factory=list)
    sessionId: str | None = None
    trigger: str | None = None
    contribute_to_global: bool = True


class DemoPingPayload(BaseModel):
    profile: DemoProfile | None = None
    query: str
    source: str = "cursor"
    min_score: float = 0.70
    scope: str = "both"


def _stable_user_id(profile: DemoProfile | None) -> str:
    if not profile:
        return "demo-user"
    if profile.email:
        return profile.email.strip().lower()
    raw = "|".join(
        [
            profile.company or "",
            profile.teamProject or "",
            profile.name or "",
            profile.role or "",
        ]
    ).strip("|")
    if not raw:
        return "demo-user"
    return f"demo_{hashlib.sha256(raw.lower().encode()).hexdigest()[:16]}"


def _transcript(messages: list[DemoMessage]) -> str:
    lines: list[str] = []
    for index, message in enumerate(messages, start=1):
        role = "assistant" if message.role == "assistant" else "user"
        content = " ".join(message.content.split())
        if content:
            lines.append(f"Turn {index} [{role}]: {content}")
    return "\n".join(lines)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


@router.post("/complete")
async def complete_conversation(payload: DemoCompletePayload) -> JSONResponse:
    if not payload.messages:
        return JSONResponse(status_code=400, content={"error": "messages are required"})

    user_id = _stable_user_id(payload.profile)
    transcript = _transcript(payload.messages)
    if not transcript:
        return JSONResponse(status_code=400, content={"error": "non-empty message content is required"})

    req = StoreSessionRequest(
        transcript=transcript,
        source="cursor",
        user_id=user_id,
        user_email=payload.profile.email.strip().lower() if payload.profile and payload.profile.email else None,
        org_id=payload.profile.company.strip().lower() if payload.profile and payload.profile.company else None,
        company=payload.profile.company.strip() if payload.profile and payload.profile.company else None,
        session_id=payload.sessionId or "",
        contribute_to_global=payload.contribute_to_global,
        participants=[
            {
                "id": user_id,
                "name": payload.profile.name if payload.profile else None,
                "role": payload.profile.role if payload.profile else None,
                "metadata": {
                    "email": payload.profile.email if payload.profile else None,
                    "company": payload.profile.company if payload.profile else None,
                    "teamProject": payload.profile.teamProject if payload.profile else None,
                },
            }
        ],
        client_metadata={"name": "orange-demo-site", "trigger": payload.trigger},
        messages=[message.model_dump() for message in payload.messages],
        metadata={
            "title": f"{payload.profile.name if payload.profile and payload.profile.name else 'Demo'} chat session",
            "profile": payload.profile.model_dump() if payload.profile else {},
        },
    )
    try:
        response = await handle_store_session(req, neo4j=get_neo4j(), chroma=get_chroma(), llm=None)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": str(exc), "backend": "orange"})

    return JSONResponse({**_jsonable(response), "backend": "orange"})


@router.post("/ping_context")
async def ping_context(payload: DemoPingPayload) -> JSONResponse:
    user_id = _stable_user_id(payload.profile)
    req = PingContextRequest(
        query=payload.query,
        user_id=user_id,
        source=payload.source,
        min_score=payload.min_score,
        user_email=payload.profile.email.strip().lower() if payload.profile and payload.profile.email else None,
        org_id=payload.profile.company.strip().lower() if payload.profile and payload.profile.company else None,
        company=payload.profile.company.strip() if payload.profile and payload.profile.company else None,
        scope=payload.scope,
    )
    try:
        response = await handle_ping_context(req, neo4j=get_neo4j(), chroma=get_chroma())
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": str(exc), "backend": "orange"})

    return JSONResponse({**_jsonable(response), "backend": "orange"})
