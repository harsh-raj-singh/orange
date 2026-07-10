from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.auth.providers.supabase import SupabaseProvider
from starlette.testclient import TestClient

from core.mcp_server import server


class RejectingTokenVerifier(TokenVerifier):
    """Deterministic verifier that never performs JWT discovery or network I/O."""

    async def verify_token(self, token: str) -> AccessToken | None:
        return None


def test_configured_mcp_app_exposes_protected_resource_and_challenges(monkeypatch) -> None:
    provider = SupabaseProvider(
        project_url="https://project-ref.supabase.co",
        base_url="https://orange.example",
        token_verifier=RejectingTokenVerifier(),
    )
    configured_mcp = FastMCP("orange-oauth-test", auth=provider)
    monkeypatch.setattr(server, "_AUTH_PROVIDER", provider)
    monkeypatch.setattr(server, "_APP", configured_mcp)

    mcp_app = server.create_http_app(path="/mcp")
    route_paths = {getattr(route, "path", None) for route in mcp_app.routes}

    assert "/.well-known/oauth-protected-resource/mcp" in route_paths
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
