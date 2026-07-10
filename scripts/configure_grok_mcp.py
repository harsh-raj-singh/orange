#!/usr/bin/env python3
"""Thin compatibility wrapper around configure_mcp.py for Grok CLI.

Prefer:

    python scripts/configure_mcp.py grok remote
    # → adds orange-remote by default (does not overwrite local stdio orange)
    python scripts/configure_mcp.py grok --name orange remote --force
    python scripts/configure_mcp.py grok local --email you@example.com

This script keeps the historical entry point working:

    python scripts/configure_grok_mcp.py remote
    python scripts/configure_grok_mcp.py --name orange-remote remote --url https://example.com/mcp
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a script without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from configure_mcp import main as configure_main  # noqa: E402


def _rewrite_historical_argv(argv: list[str]) -> list[str]:
    """Map historical `configure_grok_mcp.py [opts] remote|local ...` to configure_mcp.

    Historical shape mixed global opts with the mode subcommand. New shape is:

        configure_mcp.py grok [--name/--scope] remote [--url]
        configure_mcp.py grok [--name/--scope] local [--email]
    """

    if not argv:
        return ["grok"]

    # Already using the new provider prefix.
    if argv[0] in {"grok", "claude", "chatgpt", "generic", "url"}:
        return argv

    mode: str | None = None
    mode_index: int | None = None
    for index, token in enumerate(argv):
        if token in {"remote", "local"}:
            mode = token
            mode_index = index
            break

    if mode is None or mode_index is None:
        return ["grok", *argv]

    before = argv[:mode_index]
    after = argv[mode_index + 1 :]

    # Global opts that belong on the `grok` parser.
    grok_opts: list[str] = []
    # Mode-specific opts that belong after `remote` / `local`.
    mode_opts: list[str] = []

    index = 0
    while index < len(before):
        token = before[index]
        if token in {"--name", "--scope"} and index + 1 < len(before):
            grok_opts.extend([token, before[index + 1]])
            index += 2
            continue
        if token.startswith("--name=") or token.startswith("--scope="):
            grok_opts.append(token)
            index += 1
            continue
        # Unknown pre-mode options stay with the mode command (e.g. future flags).
        mode_opts.append(token)
        index += 1

    mode_opts.extend(after)
    return ["grok", *grok_opts, mode, *mode_opts]


def main() -> None:
    raw = sys.argv[1:]
    if raw in (["-h"], ["--help"]):
        print(__doc__ or "")
        print("Examples:")
        print("  python scripts/configure_grok_mcp.py remote")
        print("  python scripts/configure_grok_mcp.py local --email you@example.com")
        print("  python scripts/configure_grok_mcp.py --name orange-remote remote")
        print()
        print("Preferred entry point (note: --name before remote):")
        print("  python scripts/configure_mcp.py grok remote")
        print("  python scripts/configure_mcp.py grok --name orange-remote remote")
        return
    argv = _rewrite_historical_argv(raw)
    configure_main(argv)


if __name__ == "__main__":
    main()
