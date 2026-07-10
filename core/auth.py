from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from starlette.requests import Request


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """Verified Supabase identity used to scope Orange memory."""

    subject: str
    email: str | None
    claims: dict[str, Any]


def _clean_email(value: Any) -> str | None:
    cleaned = str(value or "").strip().lower()
    return cleaned or None


def _public_backend_url() -> str:
    configured = (
        os.getenv("ORANGE_PUBLIC_BACKEND_URL")
        or os.getenv("ORANGE_BACKEND_URL")
        # Render injects the public HTTPS origin for the web service.
        or os.getenv("RENDER_EXTERNAL_URL")
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or ""
    ).strip()
    if configured and not configured.startswith(("http://", "https://")):
        configured = f"https://{configured}"
    return configured.rstrip("/") or "http://127.0.0.1:8001"


def _supabase_url() -> str | None:
    value = (
        os.getenv("SUPABASE_URL")
        or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        or ""
    ).strip()
    return value.rstrip("/") or None


@lru_cache(maxsize=1)
def get_supabase_auth_provider() -> Any | None:
    """Create the FastMCP resource-server verifier once per process."""

    project_url = _supabase_url()
    if not project_url:
        return None

    from fastmcp.server.auth.providers.supabase import SupabaseProvider

    return SupabaseProvider(
        project_url=project_url,
        base_url=_public_backend_url(),
        algorithm=os.getenv("SUPABASE_JWT_ALGORITHM", "ES256").strip().upper(),
    )


def identity_from_access_token(token: Any | None) -> AuthenticatedIdentity | None:
    if token is None:
        return None
    claims = dict(getattr(token, "claims", None) or {})
    subject = str(claims.get("sub") or "").strip()
    role = str(claims.get("role") or "authenticated").strip().lower()
    if not subject or role != "authenticated":
        return None
    return AuthenticatedIdentity(
        subject=subject,
        email=_clean_email(claims.get("email")),
        claims=claims,
    )


def get_mcp_identity() -> AuthenticatedIdentity | None:
    """Return the verified identity for the active FastMCP request, if any."""

    try:
        from fastmcp.server.dependencies import get_access_token

        return identity_from_access_token(get_access_token())
    except (ImportError, RuntimeError, LookupError):
        # Stdio calls do not have an HTTP auth context. They continue to use
        # the explicit user identity supplied by the local MCP configuration.
        return None


async def verify_bearer_token(token: str) -> AuthenticatedIdentity | None:
    provider = get_supabase_auth_provider()
    if provider is None or not token:
        return None
    access_token = await provider.verify_token(token)
    return identity_from_access_token(access_token)


async def optional_request_identity(request: Request) -> AuthenticatedIdentity | None:
    """Verify a Supabase bearer token on a regular FastAPI endpoint."""

    authorization = str(request.headers.get("authorization") or "").strip()
    if not authorization:
        return None
    scheme, _, raw_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not raw_token.strip():
        return None
    return await verify_bearer_token(raw_token.strip())


async def require_request_identity(request: Request) -> AuthenticatedIdentity:
    """FastAPI dependency that fails closed for private Orange endpoints."""

    from fastapi import HTTPException

    try:
        identity = await optional_request_identity(request)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=401,
            detail="The Supabase access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if identity is None:
        raise HTTPException(
            status_code=401,
            detail="Sign in with Supabase to access Orange memory.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return identity


def reset_auth_provider_cache() -> None:
    """Test helper for environment-specific provider construction."""

    get_supabase_auth_provider.cache_clear()
