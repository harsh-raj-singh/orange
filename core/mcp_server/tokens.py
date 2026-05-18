from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TOKEN_PREFIX = "omcp_"


def normalize_email(email: str | None) -> str:
    cleaned = str(email or "").strip().lower()
    if not cleaned or not EMAIL_RE.match(cleaned):
        raise ValueError("A valid email is required")
    return cleaned


def _secret() -> bytes:
    secret = (os.getenv("ORANGE_MCP_SIGNING_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("ORANGE_MCP_SIGNING_SECRET is required to mint signed MCP tokens.")
    return secret.encode("utf-8")


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padded = data + ("=" * (-len(data) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _sign(payload: str) -> str:
    digest = hmac.new(_secret(), payload.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def mint_mcp_token(email: str, *, expires_in_days: int = 365) -> str:
    normalized_email = normalize_email(email)
    now = int(time.time())
    payload: dict[str, Any] = {
        "aud": "orange-mcp",
        "email": normalized_email,
        "iat": now,
        "exp": now + max(1, int(expires_in_days)) * 24 * 60 * 60,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _sign(encoded)
    return f"{TOKEN_PREFIX}{encoded}.{signature}"


def decode_mcp_token(token: str) -> dict[str, Any] | None:
    raw = str(token or "").strip()
    if not raw.startswith(TOKEN_PREFIX):
        return None
    try:
        encoded, signature = raw[len(TOKEN_PREFIX) :].split(".", 1)
        expected = _sign(encoded)
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_b64decode(encoded))
    except Exception:
        return None

    if payload.get("aud") != "orange-mcp":
        return None
    exp = int(payload.get("exp") or 0)
    if exp < int(time.time()):
        return None
    try:
        payload["email"] = normalize_email(str(payload.get("email") or ""))
    except ValueError:
        return None
    return payload


def verify_mcp_token(token: str) -> str | None:
    payload = decode_mcp_token(token)
    if payload is None:
        return None
    return str(payload.get("email") or "") or None
