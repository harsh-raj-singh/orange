#!/usr/bin/env python3
"""Configure Orange as a Grok CLI MCP server without copying secrets into the repo."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REMOTE_URL = "https://orange-api-production.up.railway.app/mcp"


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, text=True)


def _grok_binary() -> str:
    grok = shutil.which("grok")
    if not grok:
        raise SystemExit("Grok CLI was not found on PATH. Install or open Grok, then retry.")
    return grok


def _configure_local(args: argparse.Namespace) -> None:
    python = REPO_ROOT / "venv311" / "bin" / "python"
    if not python.exists():
        raise SystemExit(
            f"Missing {python}. Create the Python 3.11 environment and install requirements first."
        )

    command = [
        _grok_binary(),
        "mcp",
        "add",
        "--scope",
        args.scope,
        args.name,
        "-e",
        f"PYTHONPATH={REPO_ROOT}",
    ]
    if args.email:
        command.extend(["-e", f"ORANGE_USER_EMAIL={args.email.strip().lower()}"])
    command.extend(["--", str(python), "-m", "core.mcp_server.server"])
    _run(command)
    _run([_grok_binary(), "mcp", "doctor", args.name])


def _configure_remote(args: argparse.Namespace) -> None:
    command = [
        _grok_binary(),
        "mcp",
        "add",
        "--scope",
        args.scope,
        "--transport",
        "http",
        args.name,
        args.url,
    ]
    _run(command)
    print(
        f"Configured {args.name} with the Orange MCP URL. Launch Grok, open /mcps, "
        f"select {args.name}, press i, and finish the browser sign-in. Afterward, run "
        f"`grok mcp doctor {args.name}` if you want a connection check."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure Orange MCP for Grok CLI.")
    parser.add_argument("--name", default="orange", help="MCP server name (default: orange).")
    parser.add_argument(
        "--scope",
        choices=("user", "project"),
        default="user",
        help="Where Grok stores the MCP configuration (default: user).",
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    local = subparsers.add_parser("local", help="Run Orange from this checkout over stdio.")
    local.add_argument(
        "--email",
        help="Optional default identity for local private-memory writes.",
    )
    local.set_defaults(handler=_configure_local)

    remote = subparsers.add_parser(
        "remote",
        help="Use the deployed Orange MCP with browser-based OAuth sign-in.",
    )
    remote.add_argument("--url", default=DEFAULT_REMOTE_URL)
    remote.set_defaults(handler=_configure_remote)

    args = parser.parse_args()
    try:
        args.handler(args)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc


if __name__ == "__main__":
    main()
