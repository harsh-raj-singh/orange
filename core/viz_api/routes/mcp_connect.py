from __future__ import annotations

import os
from urllib.parse import urljoin

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.mcp_server.tokens import mint_mcp_token, normalize_email

router = APIRouter()


class CreateMcpTokenPayload(BaseModel):
    credential: str


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


def _google_client_ids() -> list[str]:
    values = [
        os.getenv("GOOGLE_CLIENT_ID"),
        os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
        os.getenv("NEXT_PUBLIC_GOOGLE_CLIENT_ID"),
    ]
    raw = os.getenv("GOOGLE_CLIENT_IDS", "")
    if raw.strip():
        values.extend(raw.split(","))
    return [value.strip() for value in values if value and value.strip()]


def _verify_google_credential(credential: str) -> tuple[str, str | None]:
    client_ids = _google_client_ids()
    if not client_ids:
        raise RuntimeError("GOOGLE_CLIENT_ID is required to verify Google sign-in.")

    from google.auth.transport import requests
    from google.oauth2 import id_token

    last_error: Exception | None = None
    for client_id in client_ids:
        try:
            info = id_token.verify_oauth2_token(credential, requests.Request(), client_id)
        except ValueError as exc:
            last_error = exc
            continue
        if not info.get("email_verified"):
            raise ValueError("Google account email is not verified.")
        email = normalize_email(str(info.get("email") or ""))
        name = str(info.get("name") or "").strip() or None
        return email, name
    raise ValueError(f"Google credential could not be verified: {last_error}")


@router.post("/connect")
async def create_mcp_connection(payload: CreateMcpTokenPayload, request: Request) -> JSONResponse:
    try:
        email, name = _verify_google_credential(payload.credential)
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

# Orange tools: recall_memory retrieves prior context before work.
# checkpoint_context saves important mid-session decisions to Neo4j only.
# Resource: orange_instructions is readable by Codex/Claude for protocol guidance.
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
            "name": name,
            "token": token,
            "mcp_url": mcp_url,
            "codex_config": codex_config,
            "codex_command": codex_command,
            "claude_command": claude_command,
        }
    )
