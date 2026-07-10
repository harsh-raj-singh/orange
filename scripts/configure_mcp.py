#!/usr/bin/env python3
"""Configure Orange MCP for any compatible client.

Orange exposes one remote Streamable HTTP endpoint for every provider:

    https://orange-api-x38s.onrender.com/mcp

Authentication is browser OAuth (discovery, PKCE, dynamic client registration).
Users never copy tokens or API keys.

Provider-specific subcommands are thin setup helpers only. The backend is
provider-neutral.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REMOTE_URL = "https://orange-api-x38s.onrender.com/mcp"


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, text=True)


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


def _configure_grok_local(args: argparse.Namespace) -> None:
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


def _configure_grok_remote(args: argparse.Namespace) -> None:
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
        f"Configured {args.name} with the Orange MCP URL.\n"
        f"Launch Grok, open /mcps, select {args.name}, press i, and finish browser sign-in.\n"
        f"Optional check: grok mcp doctor {args.name}"
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
    _print_header("Connect Orange · ChatGPT")
    _print_remote_url(url)
    print("ChatGPT (custom GPT / MCP connector, when available in your workspace):")
    print("  1. Create or edit a custom GPT / connector.")
    print(f"  2. Add the Orange MCP URL: {url}")
    print("  3. Choose OAuth / browser sign-in when the client offers it.")
    print("  4. Approve Orange access in the browser; do not paste tokens or keys.")
    print()
    print(
        "If your ChatGPT surface only supports Actions with a fixed secret, prefer "
        "a full MCP client (Grok, Claude Code, Cursor, etc.) that supports "
        "OAuth-protected MCP resources."
    )


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
            "One remote URL; browser OAuth; no copied secrets."
        )
    )
    subparsers = parser.add_subparsers(dest="provider", required=True)

    # --- Grok (thin automated helper) ---
    grok = subparsers.add_parser("grok", help="Configure Grok CLI MCP entry.")
    grok.add_argument("--name", default="orange", help="MCP server name (default: orange).")
    grok.add_argument(
        "--scope",
        choices=("user", "project"),
        default="user",
        help="Where Grok stores the MCP configuration (default: user).",
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
        help="Use the deployed Orange MCP with browser-based OAuth sign-in.",
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
        help="Print ChatGPT connector setup steps (no local mutation).",
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
