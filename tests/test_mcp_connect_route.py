from __future__ import annotations

from fastapi.testclient import TestClient

from core.viz_api.main import app


def test_mcp_connect_mints_signed_token(monkeypatch):
    monkeypatch.setenv("ORANGE_MCP_SIGNING_SECRET", "test-secret")
    monkeypatch.setenv("ORANGE_PUBLIC_BACKEND_URL", "https://orange.example")

    client = TestClient(app)
    response = client.post("/mcp/connect", json={"email": "DEV@example.com"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == "dev@example.com"
    assert payload["token"].startswith("omcp_")
    assert payload["mcp_url"] == "https://orange.example/mcp/"
    assert "bearer_token_env_var" in payload["codex_config"]


def test_mcp_connect_requires_signing_secret(monkeypatch):
    monkeypatch.delenv("ORANGE_MCP_SIGNING_SECRET", raising=False)

    client = TestClient(app)
    response = client.post("/mcp/connect", json={"email": "dev@example.com"})

    assert response.status_code == 503
