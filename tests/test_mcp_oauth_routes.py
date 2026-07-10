from __future__ import annotations

import json
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.auth.providers.supabase import SupabaseProvider
from starlette.testclient import TestClient

from core.auth import AuthenticatedIdentity
from core.mcp_server import server


class RejectingTokenVerifier(TokenVerifier):
    """Deterministic verifier that never performs JWT discovery or network I/O."""

    def __init__(self) -> None:
        super().__init__()

    async def verify_token(self, token: str) -> AccessToken | None:
        return None


class AcceptingTokenVerifier(TokenVerifier):
    """Verifier that accepts a single known bearer token."""

    def __init__(self, token: str = "valid-access-token") -> None:
        super().__init__()
        self.token = token
        self.seen: list[str] = []

    async def verify_token(self, token: str) -> AccessToken | None:
        self.seen.append(token)
        if token != self.token:
            return None
        return AccessToken(
            token=token,
            client_id="mcp-client",
            scopes=[],
            claims={
                "sub": "auth-user-1",
                "email": "dev@example.com",
                "role": "authenticated",
                "exp": 4_102_444_800,
            },
        )


def _configured_app(
    monkeypatch,
    *,
    token_verifier: TokenVerifier | None = None,
) -> Any:
    provider = SupabaseProvider(
        project_url="https://project-ref.supabase.co",
        base_url="https://orange.example",
        token_verifier=token_verifier or RejectingTokenVerifier(),
    )
    configured_mcp = FastMCP("orange-oauth-test", auth=provider)
    monkeypatch.setattr(server, "_AUTH_PROVIDER", provider)
    monkeypatch.setattr(server, "_APP", configured_mcp)
    return server.create_http_app(path="/mcp"), provider


def test_configured_mcp_app_exposes_protected_resource_and_challenges(monkeypatch) -> None:
    mcp_app, _provider = _configured_app(monkeypatch)
    route_paths = {getattr(route, "path", None) for route in mcp_app.routes}

    assert "/.well-known/oauth-protected-resource/mcp" in route_paths
    assert "/.well-known/oauth-authorization-server" in route_paths
    assert "/mcp" in route_paths

    with TestClient(mcp_app) as client:
        metadata_response = client.get("/.well-known/oauth-protected-resource/mcp")
        protected_response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )

    assert metadata_response.status_code == 200
    assert metadata_response.json() == {
        "resource": "https://orange.example/mcp",
        "authorization_servers": ["https://project-ref.supabase.co/auth/v1"],
        "scopes_supported": [],
        "bearer_methods_supported": ["header"],
    }

    assert protected_response.status_code == 401
    assert protected_response.json()["error"] == "invalid_token"
    challenge = protected_response.headers["www-authenticate"]
    assert challenge.startswith('Bearer error="invalid_token"')
    assert (
        'resource_metadata="https://orange.example/.well-known/oauth-protected-resource/mcp"'
        in challenge
    )


def test_oauth_authorization_server_forwards_registration_and_pkce(monkeypatch) -> None:
    """AS metadata must advertise DCR + PKCE so clients never need hardcoded secrets."""

    mcp_app, _provider = _configured_app(monkeypatch)

    supabase_metadata = {
        "issuer": "https://project-ref.supabase.co/auth/v1",
        "authorization_endpoint": "https://project-ref.supabase.co/auth/v1/oauth/authorize",
        "token_endpoint": "https://project-ref.supabase.co/auth/v1/oauth/token",
        "registration_endpoint": "https://project-ref.supabase.co/auth/v1/oauth/clients/register",
        "code_challenge_methods_supported": ["S256", "plain"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
        "response_types_supported": ["code"],
    }

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, url: str) -> httpx.Response:
            assert url.endswith("/.well-known/oauth-authorization-server")
            request = httpx.Request("GET", url)
            return httpx.Response(200, json=supabase_metadata, request=request)

    # SupabaseProvider closes over the httpx import in its own module.
    import fastmcp.server.auth.providers.supabase as supabase_provider

    monkeypatch.setattr(supabase_provider.httpx, "AsyncClient", FakeAsyncClient)

    with TestClient(mcp_app) as client:
        response = client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    body = response.json()
    assert body["registration_endpoint"].endswith("/oauth/clients/register")
    assert "S256" in body["code_challenge_methods_supported"]
    assert "authorization_code" in body["grant_types_supported"]
    # Public clients use PKCE with auth method "none" — no hardcoded client secret.
    assert "none" in body["token_endpoint_auth_methods_supported"]


def _pkce_s256_challenge(code_verifier: str) -> str:
    """RFC 7636 S256 code_challenge = BASE64URL(SHA256(verifier))."""

    import base64
    import hashlib

    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def test_mocked_dcr_and_pkce_authorization_code_exchange() -> None:
    """Exercise dynamic client registration + PKCE token exchange (mocked AS).

    Orange does not host registration/token endpoints itself — Supabase Auth
    does. This test simulates the MCP client side of that flow so we verify more
    than metadata advertisement: public-client DCR, S256 challenge construction,
    and authorization_code + code_verifier token exchange without a client secret.
    """

    import base64
    import hashlib
    import secrets

    as_base = "https://project-ref.supabase.co/auth/v1"
    registration_endpoint = f"{as_base}/oauth/clients/register"
    token_endpoint = f"{as_base}/oauth/token"
    authorization_endpoint = f"{as_base}/oauth/authorize"
    redirect_uri = "http://127.0.0.1:54321/callback"

    # --- Client generates PKCE pair (S256) ---
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _pkce_s256_challenge(code_verifier)
    assert code_challenge == base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert len(code_challenge) >= 43

    registered: dict[str, Any] = {}
    token_requests: list[dict[str, Any]] = []
    issued_access_token = "access-token-from-pkce-exchange"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path.endswith("/oauth/clients/register"):
            body = json.loads(request.content.decode("utf-8"))
            registered.update(body)
            # Public MCP clients must not require a pre-shared client secret.
            assert body.get("token_endpoint_auth_method") == "none"
            assert redirect_uri in (body.get("redirect_uris") or [])
            assert "authorization_code" in (body.get("grant_types") or [])
            return httpx.Response(
                201,
                json={
                    "client_id": "dyn-client-orange-mcp",
                    "client_id_issued_at": 1_720_000_000,
                    "token_endpoint_auth_method": "none",
                    "redirect_uris": body["redirect_uris"],
                    "grant_types": body["grant_types"],
                    "response_types": body.get("response_types") or ["code"],
                },
                request=request,
            )

        if request.method == "POST" and path.endswith("/oauth/token"):
            form = dict(httpx.QueryParams(request.content.decode("utf-8")))
            token_requests.append(form)
            assert form.get("grant_type") == "authorization_code"
            assert form.get("code") == "auth-code-from-browser"
            assert form.get("redirect_uri") == redirect_uri
            assert form.get("client_id") == "dyn-client-orange-mcp"
            assert form.get("code_verifier") == code_verifier
            # No client_secret for public PKCE clients.
            assert "client_secret" not in form
            return httpx.Response(
                200,
                json={
                    "access_token": issued_access_token,
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "refresh_token": "refresh-token-from-pkce-exchange",
                },
                request=request,
            )

        return httpx.Response(404, json={"error": "not_found"}, request=request)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url=as_base) as client:
        # 1) Dynamic Client Registration (RFC 7591)
        reg_response = client.post(
            registration_endpoint,
            json={
                "client_name": "orange-mcp-test-client",
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        )
        assert reg_response.status_code == 201
        client_id = reg_response.json()["client_id"]
        assert client_id == "dyn-client-orange-mcp"
        assert registered["token_endpoint_auth_method"] == "none"

        # 2) Authorization request would open the browser with code_challenge.
        #    We assert the URL shape a compliant client builds (no network).
        auth_url = httpx.URL(
            authorization_endpoint,
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "openid email offline_access",
            },
        )
        assert auth_url.params["code_challenge_method"] == "S256"
        assert auth_url.params["code_challenge"] == code_challenge
        assert auth_url.params["client_id"] == client_id

        # 3) After browser consent, exchange authorization_code + code_verifier.
        token_response = client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": "auth-code-from-browser",
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": code_verifier,
            },
        )
        assert token_response.status_code == 200
        tokens = token_response.json()
        assert tokens["access_token"] == issued_access_token
        assert tokens["token_type"].lower() == "bearer"
        assert tokens.get("refresh_token")
        assert len(token_requests) == 1
        assert token_requests[0]["code_verifier"] == code_verifier


def test_access_token_from_pkce_exchange_authenticates_mcp(monkeypatch) -> None:
    """Token obtained via (mocked) PKCE exchange is accepted by the resource server."""

    verifier = AcceptingTokenVerifier(token="access-token-from-pkce-exchange")
    mcp_app, _provider = _configured_app(monkeypatch, token_verifier=verifier)

    with TestClient(mcp_app) as client:
        # Without token → still challenged.
        bare = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "pkce-client", "version": "1"},
                },
            },
        )
        assert bare.status_code == 401

        # With the token from the exchange → verifier is invoked with that bearer.
        authorized = client.post(
            "/mcp",
            headers={"Authorization": "Bearer access-token-from-pkce-exchange"},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "pkce-client", "version": "1"},
                },
            },
        )

    assert "access-token-from-pkce-exchange" in verifier.seen
    # FastMCP may return 200 on initialize or continue the streamable session;
    # the critical contract is that the exchanged bearer was accepted for auth.
    assert authorized.status_code != 401
    assert authorized.status_code < 500


def test_invalid_bearer_token_is_rejected_with_401_challenge(monkeypatch) -> None:
    verifier = AcceptingTokenVerifier()
    mcp_app, _provider = _configured_app(monkeypatch, token_verifier=verifier)

    with TestClient(mcp_app) as client:
        response = client.post(
            "/mcp",
            headers={"Authorization": "Bearer wrong-token"},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )

    assert response.status_code == 401
    assert verifier.seen == ["wrong-token"]
    assert "resource_metadata=" in response.headers["www-authenticate"]


def test_authenticated_identity_overrides_client_supplied_email(monkeypatch) -> None:
    """Remote MCP must scope to the verified Supabase subject, not a spoofed email."""

    monkeypatch.setattr(
        server,
        "get_mcp_identity",
        lambda: AuthenticatedIdentity(
            subject="auth-user-1",
            email="owner@example.com",
            claims={"sub": "auth-user-1", "email": "owner@example.com", "role": "authenticated"},
        ),
    )

    assert server._default_user_email("attacker@evil.com") == "owner@example.com"
    assert server._default_user_id("spoofed-local-id", "attacker@evil.com") == "auth-user-1"
    assert server._auth_metadata() == {"auth_user_id": "auth-user-1"}


def test_get_job_status_rejects_cross_user_job(monkeypatch) -> None:
    class FakeRepository:
        def get_memory_write_job(self, job_id: str) -> dict[str, Any]:
            return {
                "id": job_id,
                "status": "succeeded",
                "user_email": "owner@example.com",
                "session_id": "session-1",
                "source": "mcp",
                "attempt_count": 1,
                "max_attempts": 3,
                "available_at": None,
                "last_attempt_at": None,
                "completed_at": None,
                "dead_lettered_at": None,
                "error": None,
                "result": {"ok": True},
            }

    monkeypatch.setattr(server, "get_postgres_store", lambda: FakeRepository())
    monkeypatch.setattr(
        server,
        "get_mcp_identity",
        lambda: AuthenticatedIdentity(
            subject="auth-user-2",
            email="other@example.com",
            claims={"sub": "auth-user-2", "email": "other@example.com", "role": "authenticated"},
        ),
    )

    import asyncio
    from core.mcp_server.server import get_job_status

    tool = getattr(get_job_status, "fn", get_job_status)
    try:
        asyncio.run(tool(job_id="job-1", user_email="other@example.com"))
        raised = False
    except PermissionError as exc:
        raised = True
        assert "different user" in str(exc).lower()
    assert raised is True
