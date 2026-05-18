from __future__ import annotations

import os
from urllib.parse import urljoin

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.mcp_server.tokens import mint_mcp_token, normalize_email

router = APIRouter()


class CreateMcpTokenPayload(BaseModel):
    email: str


def _public_backend_url(request: Request) -> str:
    configured = (
        os.getenv("ORANGE_PUBLIC_BACKEND_URL")
        or os.getenv("ORANGE_BACKEND_URL")
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or ""
    ).strip()
    if configured and not configured.startswith(("http://", "https://")):
        configured = f"https://{configured}"
    return configured.rstrip("/") if configured else str(request.base_url).rstrip("/")


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


@router.post("/connect")
async def create_mcp_connection(payload: CreateMcpTokenPayload, request: Request) -> JSONResponse:
    try:
        email = normalize_email(payload.email)
        token = mint_mcp_token(email)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except RuntimeError as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})

    backend_url = _public_backend_url(request)
    mcp_url = urljoin(f"{backend_url}/", "mcp/")
    codex_config = f"""[mcp_servers.orange]
url = \"{mcp_url}\"
bearer_token_env_var = \"ORANGE_MCP_TOKEN\"
startup_timeout_sec = 20
tool_timeout_sec = 180
enabled = true
"""
    codex_command = (
        f"export ORANGE_MCP_TOKEN={_shell_quote(token)}\n"
        "codex"
    )
    claude_command = (
        "claude mcp add --transport http --scope user orange "
        f"{mcp_url} --header \"Authorization: Bearer {token}\""
    )

    return JSONResponse(
        {
            "email": email,
            "token": token,
            "mcp_url": mcp_url,
            "codex_config": codex_config,
            "codex_command": codex_command,
            "claude_command": claude_command,
        }
    )
