from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from fastmcp.server.auth import AccessToken
from starlette.requests import Request

from core import auth


class StubSupabaseProvider:
    def __init__(self, result: AccessToken | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.seen_tokens: list[str] = []

    async def verify_token(self, token: str) -> AccessToken | None:
        self.seen_tokens.append(token)
        if self.error is not None:
            raise self.error
        return self.result


def _private_app() -> FastAPI:
    app = FastAPI()

    async def require_identity(request: Request) -> auth.AuthenticatedIdentity:
        # Keep the production verifier under test while giving this tiny test
        # app the concrete Request annotation FastAPI needs for dependency
        # injection.
        return await auth.require_request_identity(request)

    @app.get("/private")
    async def private_route(
        identity: auth.AuthenticatedIdentity = Depends(require_identity),
    ) -> dict[str, Any]:
        return {
            "subject": identity.subject,
            "email": identity.email,
            "claims": identity.claims,
        }

    return app


def test_verified_supabase_claims_become_scoped_identity(monkeypatch) -> None:
    access_token = AccessToken(
        token="verified-token",
        client_id="grok-cli",
        scopes=[],
        claims={
            "sub": "auth-user-123",
            "email": "  Developer@Example.COM ",
            "role": "authenticated",
            "organization_id": "org-456",
        },
    )
    provider = StubSupabaseProvider(result=access_token)
    monkeypatch.setattr(auth, "get_supabase_auth_provider", lambda: provider)

    client = TestClient(_private_app())
    response = client.get(
        "/private",
        headers={"Authorization": "Bearer verified-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "subject": "auth-user-123",
        "email": "developer@example.com",
        "claims": {
            "sub": "auth-user-123",
            "email": "  Developer@Example.COM ",
            "role": "authenticated",
            "organization_id": "org-456",
        },
    }
    assert provider.seen_tokens == ["verified-token"]


def test_private_rest_route_rejects_missing_bearer_without_calling_provider(monkeypatch) -> None:
    provider = StubSupabaseProvider()
    monkeypatch.setattr(auth, "get_supabase_auth_provider", lambda: provider)

    response = TestClient(_private_app()).get("/private")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Sign in with Supabase to access Orange memory."}
    assert provider.seen_tokens == []


def test_private_rest_route_rejects_invalid_bearer_from_provider(monkeypatch) -> None:
    provider = StubSupabaseProvider(error=ValueError("signature rejected"))
    monkeypatch.setattr(auth, "get_supabase_auth_provider", lambda: provider)

    response = TestClient(_private_app()).get(
        "/private",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "The Supabase access token is invalid or expired."}
    assert provider.seen_tokens == ["invalid-token"]
