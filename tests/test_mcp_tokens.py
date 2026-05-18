from __future__ import annotations

from core.mcp_server.tokens import decode_mcp_token, mint_mcp_token, verify_mcp_token


def test_signed_mcp_token_round_trip(monkeypatch):
    monkeypatch.setenv("ORANGE_MCP_SIGNING_SECRET", "test-secret")

    token = mint_mcp_token("DEV@Example.com")

    assert token.startswith("omcp_")
    assert verify_mcp_token(token) == "dev@example.com"
    payload = decode_mcp_token(token)
    assert payload is not None
    assert payload["exp"] > payload["iat"]


def test_signed_mcp_token_rejects_wrong_secret(monkeypatch):
    monkeypatch.setenv("ORANGE_MCP_SIGNING_SECRET", "first-secret")
    token = mint_mcp_token("dev@example.com")

    monkeypatch.setenv("ORANGE_MCP_SIGNING_SECRET", "second-secret")

    assert verify_mcp_token(token) is None
