from __future__ import annotations

from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import configure_mcp  # noqa: E402


def test_remote_defaults_to_orange_remote(monkeypatch) -> None:
    captured: list[list[str]] = []

    monkeypatch.setattr(configure_mcp, "_grok_binary", lambda: "grok")
    monkeypatch.setattr(configure_mcp, "_list_grok_servers", lambda: [])
    monkeypatch.setattr(
        configure_mcp,
        "_run",
        lambda command, check=True: captured.append(list(command)) or type(
            "R", (), {"returncode": 0}
        )(),
    )

    configure_mcp.main(["grok", "remote"])

    assert captured
    assert "orange-remote" in captured[0]
    assert "https://orange-api-x38s.onrender.com/mcp" in captured[0]


def test_remote_refuses_to_overwrite_existing_without_force(monkeypatch) -> None:
    monkeypatch.setattr(configure_mcp, "_grok_binary", lambda: "grok")
    monkeypatch.setattr(
        configure_mcp,
        "_list_grok_servers",
        lambda: [
            {
                "name": "orange-remote",
                "url": "https://orange-api-x38s.onrender.com/mcp",
            }
        ],
    )

    with pytest.raises(SystemExit) as exc:
        configure_mcp.main(["grok", "remote"])

    assert "already exists" in str(exc.value)


def test_remote_force_overwrites_existing(monkeypatch) -> None:
    captured: list[list[str]] = []
    monkeypatch.setattr(configure_mcp, "_grok_binary", lambda: "grok")
    monkeypatch.setattr(
        configure_mcp,
        "_list_grok_servers",
        lambda: [{"name": "orange-remote", "url": "https://old.example/mcp"}],
    )
    monkeypatch.setattr(
        configure_mcp,
        "_run",
        lambda command, check=True: captured.append(list(command)) or type(
            "R", (), {"returncode": 0}
        )(),
    )

    configure_mcp.main(["grok", "--force", "remote"])

    assert captured
    assert "orange-remote" in captured[0]


def test_local_defaults_to_orange(monkeypatch) -> None:
    captured: list[list[str]] = []
    monkeypatch.setattr(configure_mcp, "_grok_binary", lambda: "grok")
    monkeypatch.setattr(configure_mcp, "_list_grok_servers", lambda: [])
    monkeypatch.setattr(
        configure_mcp,
        "_run",
        lambda command, check=True: captured.append(list(command)) or type(
            "R", (), {"returncode": 0}
        )(),
    )
    original_exists = Path.exists

    def _exists(self: Path) -> bool:
        if str(self).endswith("venv311/bin/python"):
            return True
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", _exists)

    configure_mcp.main(["grok", "local", "--email", "dev@example.com"])

    assert any(cmd and cmd[-1] == "core.mcp_server.server" for cmd in captured)
    # Local default name is "orange" (not orange-remote).
    add_cmd = next(cmd for cmd in captured if "add" in cmd)
    assert "orange" in add_cmd
    assert "orange-remote" not in add_cmd
