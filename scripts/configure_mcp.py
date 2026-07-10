#!/usr/bin/env python3
"""Configure Orange MCP for any compatible client.

Orange exposes one remote Streamable HTTP endpoint for every provider:

    https://orange-api-x38s.onrender.com/mcp

Authentication is browser OAuth (discovery, PKCE, dynamic client registration).
Users never copy tokens or API keys.

Provider-specific subcommands are thin setup helpers only. The backend is
provider-neutral.

Remote Grok onboarding defaults to the server name ``orange-remote`` so a
working local stdio ``orange`` entry is not overwritten during rollout.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REMOTE_URL = "https://orange-api-x38s.onrender.com/mcp"
DEFAULT_REMOTE_NAME = "orange-remote"
DEFAULT_LOCAL_NAME = "orange"


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, text=True)


def _run_capture(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True, capture_output=True)


def _print_header(title: str) -> None:
    print(title)
    print("=" * len(title))


def _print_remote_url(url: str) -> None:
    print(f"Orange MCP URL (all clients):\n  {url}\n")
    print(
        "Sign-in is browser OAuth. No bearer token, API key, or header is required.\n"
    )


def _grok_binary() -> str:
    grok = shutil.which("grok")
    if not grok:
        raise SystemExit("Grok CLI was not found on PATH. Install or open Grok, then retry.")
    return grok


def _list_grok_servers() -> list[dict[str, Any]]:
    """Return configured Grok MCP servers.

    Fails closed when inspection fails. An empty list means the command
    succeeded and no servers are configured — never treat a list/parse error
    as "no servers," which would allow overwriting without --force.
    """

    result = _run_capture([_grok_binary(), "mcp", "list", "--json"])
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise SystemExit(
            "Could not inspect existing Grok MCP servers "
            f"(`grok mcp list --json` failed: {detail}).\n"
            "Refusing to add or overwrite without a successful inventory "
            "(including with --force). Fix the Grok CLI error and retry."
        )
    if not stdout:
        raise SystemExit(
            "Could not inspect existing Grok MCP servers "
            "(`grok mcp list --json` returned empty output).\n"
            "Refusing to add/overwrite without a successful inventory."
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            "Could not inspect existing Grok MCP servers "
            f"(`grok mcp list --json` produced invalid JSON: {exc}).\n"
            "Refusing to add/overwrite without a successful inventory."
        ) from exc
    if not isinstance(payload, list):
        raise SystemExit(
            "Could not inspect existing Grok MCP servers "
            "(`grok mcp list --json` did not return a JSON array).\n"
            "Refusing to add/overwrite without a successful inventory."
        )
    # Only a real empty array means no servers. Non-object elements (null,
    # strings, etc.) make the inventory untrustworthy — do not filter them
    # into [] and silently proceed.
    invalid_indexes = [
        index for index, item in enumerate(payload) if not isinstance(item, dict)
    ]
    if invalid_indexes:
        raise SystemExit(
            "Could not inspect existing Grok MCP servers "
            "(`grok mcp list --json` returned a JSON array with non-object "
            f"entries at index(es) {invalid_indexes}).\n"
            "Refusing to add/overwrite without a successful inventory."
        )
    return list(payload)


def _find_grok_server(name: str) -> dict[str, Any] | None:
    for item in _list_grok_servers():
        if str(item.get("name") or "").strip() == name:
            return item
    return None


def _describe_server(entry: dict[str, Any]) -> str:
    if entry.get("url"):
        return f"http {entry.get('url')}"
    command = entry.get("command") or ""
    args = entry.get("args") or []
    if isinstance(args, list):
        joined = " ".join(str(part) for part in args)
        return f"stdio {command} {joined}".strip()
    return "existing entry"


def _ensure_name_available(name: str, *, force: bool) -> None:
    existing = _find_grok_server(name)
    if existing is None:
        return
    detail = _describe_server(existing)
    if force:
        print(
            f"Warning: overwriting existing Grok MCP server '{name}' ({detail}) because --force was set."
        )
        return
    raise SystemExit(
        f"Grok MCP server '{name}' already exists ({detail}).\n"
        f"For remote rollout use: python scripts/configure_mcp.py grok --name {DEFAULT_REMOTE_NAME} remote\n"
        f"Or pass --force to overwrite '{name}'."
    )


def _configure_grok_local(args: argparse.Namespace) -> None:
    python = REPO_ROOT / "venv311" / "bin" / "python"
    if not python.exists():
        raise SystemExit(
            f"Missing {python}. Create the Python 3.11 environment and install requirements first."
        )

    name = (args.name or DEFAULT_LOCAL_NAME).strip() or DEFAULT_LOCAL_NAME
    _ensure_name_available(name, force=bool(args.force))

    command = [
        _grok_binary(),
        "mcp",
        "add",
        "--scope",
        args.scope,
        name,
        "-e",
        f"PYTHONPATH={REPO_ROOT}",
    ]
    if args.email:
        command.extend(["-e", f"ORANGE_USER_EMAIL={args.email.strip().lower()}"])
    command.extend(["--", str(python), "-m", "core.mcp_server.server"])
    _run(command)
    _run([_grok_binary(), "mcp", "doctor", name])


def _configure_grok_remote(args: argparse.Namespace) -> None:
    name = (args.name or DEFAULT_REMOTE_NAME).strip() or DEFAULT_REMOTE_NAME
    _ensure_name_available(name, force=bool(args.force))

    command = [
        _grok_binary(),
        "mcp",
        "add",
        "--scope",
        args.scope,
        "--transport",
        "http",
        name,
        args.url,
    ]
    _run(command)
    print(
        f"Configured {name} with the Orange MCP URL.\n"
        f"Launch Grok, open /mcps, select {name}, press i, and finish browser sign-in.\n"
        f"Optional check: grok mcp doctor {name}\n"
        f"After remote works, promote to '{DEFAULT_LOCAL_NAME}' only if you intend to replace local stdio."
    )


def _print_claude_instructions(args: argparse.Namespace) -> None:
    url = args.url
    _print_header("Connect Orange · Claude Code / Claude.ai")
    _print_remote_url(url)
    print("Claude Code (CLI):")
    print(f"  claude mcp add --transport http orange {url}")
    print()
    print("Or add to .mcp.json / Claude desktop config:")
    print(
        "  {\n"
        '    "mcpServers": {\n'
        '      "orange": {\n'
        '        "type": "http",\n'
        f'        "url": "{url}"\n'
        "      }\n"
        "    }\n"
        "  }"
    )
    print()
    print("Claude.ai custom connector:")
    print("  1. Open Settings → Connectors (or Custom integrations).")
    print(f"  2. Add an MCP server with URL: {url}")
    print("  3. Complete the browser login and consent when prompted.")
    print("  4. No token paste — OAuth discovery + PKCE handles credentials.")


def _print_chatgpt_instructions(args: argparse.Namespace) -> None:
    url = args.url
    _print_header("Connect Orange · ChatGPT (Developer mode)")
    _print_remote_url(url)
    print("Official flow (not Custom GPT Actions):")
    print("  Docs: https://developers.openai.com/api/docs/guides/developer-mode")
    print("  Help: https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt")
    print()
    print("1. Enable Developer mode")
    print("   ChatGPT web → Settings → Security and login (or Settings → Apps → Advanced Settings)")
    print("   → turn on Developer mode.")
    print("   On Business/Enterprise/Edu, a workspace admin may need to allow this first.")
    print()
    print("2. Create a developer-mode App for the remote MCP server")
    print("   Open Settings → Plugins (https://chatgpt.com/plugins) or Apps → Create.")
    print("   Use + to create a developer-mode app (only available after Developer mode is on).")
    print("   Supported transports: SSE and streaming HTTP.")
    print()
    print("3. Configure Orange")
    print(f"   MCP server URL: {url}")
    print("   Authentication: OAuth (not a static secret / Custom GPT Action key).")
    print("   Click Scan Tools, complete the browser Orange login/consent, then Create.")
    print()
    print("4. Use in a chat")
    print("   Open a conversation → Plus menu → Developer mode → select the Orange app.")
    print("   Call orange_status / recall_memory / complete_conversation as needed.")
    print("   Write tools may require confirmation; Orange marks recall tools readOnlyHint.")
    print()
    print("Do not configure Orange via Custom GPT Actions. That path is not the MCP client flow.")


def _print_generic_instructions(args: argparse.Namespace) -> None:
    url = args.url
    _print_header("Connect Orange · Generic MCP client")
    _print_remote_url(url)
    print("Any Streamable HTTP MCP client that supports OAuth:")
    print(f"  1. Point the client at: {url}")
    print("  2. Allow discovery of the protected-resource metadata.")
    print("  3. Complete dynamic client registration + PKCE browser login.")
    print("  4. Use tools: recall_memory → checkpoint_context → complete_conversation.")
    print()
    print("Example config fragment (no Authorization header):")
    print(
        "  {\n"
        '    "mcpServers": {\n'
        '      "orange": {\n'
        '        "type": "http",\n'
        f'        "url": "{url}"\n'
        "      }\n"
        "    }\n"
        "  }"
    )
    print()
    print("Discovery checks:")
    base = url.removesuffix("/mcp").rstrip("/")
    print(f"  curl {base}/.well-known/oauth-protected-resource/mcp")
    print(f"  curl {base}/.well-known/oauth-authorization-server")


def _print_url(args: argparse.Namespace) -> None:
    print(args.url)


def _add_url_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--url",
        default=DEFAULT_REMOTE_URL,
        help=f"Orange MCP URL (default: {DEFAULT_REMOTE_URL}).",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Configure Orange MCP for Grok, Claude, ChatGPT, or any MCP client. "
            "One remote URL; browser OAuth; no copied secrets. "
            f"Remote Grok defaults to name '{DEFAULT_REMOTE_NAME}'."
        )
    )
    subparsers = parser.add_subparsers(dest="provider", required=True)

    # --- Grok (thin automated helper) ---
    grok = subparsers.add_parser("grok", help="Configure Grok CLI MCP entry.")
    grok.add_argument(
        "--name",
        default=None,
        help=(
            f"MCP server name. Defaults: remote={DEFAULT_REMOTE_NAME}, "
            f"local={DEFAULT_LOCAL_NAME}."
        ),
    )
    grok.add_argument(
        "--scope",
        choices=("user", "project"),
        default="user",
        help="Where Grok stores the MCP configuration (default: user).",
    )
    grok.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing Grok MCP server with the same name.",
    )
    grok_sub = grok.add_subparsers(dest="mode", required=True)

    grok_local = grok_sub.add_parser("local", help="Run Orange from this checkout over stdio.")
    grok_local.add_argument(
        "--email",
        help="Optional default identity for local private-memory writes.",
    )
    grok_local.set_defaults(handler=_configure_grok_local)

    grok_remote = grok_sub.add_parser(
        "remote",
        help=(
            f"Use the deployed Orange MCP with browser OAuth "
            f"(default name: {DEFAULT_REMOTE_NAME})."
        ),
    )
    _add_url_arg(grok_remote)
    grok_remote.set_defaults(handler=_configure_grok_remote)

    # --- Instruction-only providers ---
    claude = subparsers.add_parser(
        "claude",
        help="Print Claude Code / Claude.ai setup steps (no local mutation).",
    )
    _add_url_arg(claude)
    claude.set_defaults(handler=_print_claude_instructions)

    chatgpt = subparsers.add_parser(
        "chatgpt",
        help="Print ChatGPT Developer mode setup steps (no local mutation).",
    )
    _add_url_arg(chatgpt)
    chatgpt.set_defaults(handler=_print_chatgpt_instructions)

    generic = subparsers.add_parser(
        "generic",
        help="Print generic MCP client setup steps (no local mutation).",
    )
    _add_url_arg(generic)
    generic.set_defaults(handler=_print_generic_instructions)

    show_url = subparsers.add_parser("url", help="Print the Orange MCP URL and exit.")
    _add_url_arg(show_url)
    show_url.set_defaults(handler=_print_url)

    args = parser.parse_args(argv)
    try:
        args.handler(args)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc


if __name__ == "__main__":
    main()
