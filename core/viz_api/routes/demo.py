from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.auth import AuthenticatedIdentity, require_request_identity
from core.mcp_server.handlers import handle_recall_memory, handle_store_session
from core.mcp_server.models import RecallMemoryRequest, StoreSessionRequest
from core.viz_api.dependencies import get_memory_repository

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


class DemoRecallPayload(BaseModel):
    profile: DemoProfile | None = None
    query: str
    source: str = "cursor"
    min_score: float = 0.70
    scope: str = "both"


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
async def complete_conversation(
    payload: DemoCompletePayload,
    identity: AuthenticatedIdentity = Depends(require_request_identity),
) -> JSONResponse:
    if not payload.messages:
        return JSONResponse(status_code=400, content={"error": "messages are required"})

    user_id = identity.subject
    transcript = _transcript(payload.messages)
    if not transcript:
        return JSONResponse(status_code=400, content={"error": "non-empty message content is required"})

    req = StoreSessionRequest(
        transcript=transcript,
        source="cursor",
        user_id=user_id,
        user_email=identity.email,
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
                    "email": identity.email,
                    "company": payload.profile.company if payload.profile else None,
                    "teamProject": payload.profile.teamProject if payload.profile else None,
                },
            }
        ],
        client_metadata={"name": "orange-demo-site", "trigger": payload.trigger},
        messages=[message.model_dump() for message in payload.messages],
        metadata={
            "title": f"{payload.profile.name if payload.profile and payload.profile.name else 'Demo'} chat session",
            "profile": {
                **(payload.profile.model_dump() if payload.profile else {}),
                "email": identity.email,
            },
            "auth_user_id": identity.subject,
        },
    )
    try:
        response = await handle_store_session(
            req,
            repository=get_memory_repository(),
            llm=None,
            enqueue_only=(
                os.getenv("ORANGE_MEMORY_WRITE_MODE", "inline").strip().lower()
                == "queued"
            ),
        )
    except PermissionError as exc:
        return JSONResponse(status_code=403, content={"error": str(exc), "backend": "orange"})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": str(exc), "backend": "orange"})

    return JSONResponse({**_jsonable(response), "backend": "orange"})


@router.post("/recall_memory")
async def recall_memory(
    payload: DemoRecallPayload,
    identity: AuthenticatedIdentity = Depends(require_request_identity),
) -> JSONResponse:
    user_id = identity.subject
    req = RecallMemoryRequest(
        query=payload.query,
        user_id=user_id,
        source=payload.source,
        min_score=payload.min_score,
        user_email=identity.email,
        org_id=payload.profile.company.strip().lower() if payload.profile and payload.profile.company else None,
        company=payload.profile.company.strip() if payload.profile and payload.profile.company else None,
        scope=payload.scope,
    )
    try:
        response = await handle_recall_memory(req, repository=get_memory_repository())
    except PermissionError as exc:
        return JSONResponse(status_code=403, content={"error": str(exc), "backend": "orange"})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": str(exc), "backend": "orange"})

    return JSONResponse({**_jsonable(response), "backend": "orange"})
