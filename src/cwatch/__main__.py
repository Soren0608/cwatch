"""
cwatch.__main__
~~~~~~~~~~~~~~~
CLI entry point.  Invoked as `cwatch` or `python -m cwatch`.

Usage
-----
  cwatch                      # live dashboard, refresh every 60s
  cwatch --interval 30        # refresh every 30s
  cwatch --once               # print one line and exit (tmux / scripting)
  cwatch --json               # dump raw JSON and exit
  cwatch --token sk-ant-...   # pass token explicitly
  cwatch --creds ~/path.json  # custom credentials file
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime

from . import __version__
from .api import APIError, AuthError, fetch
from .credentials import get_token
from .render import clear_screen, dashboard, oneliner

# ─── ANSI for error messages ──────────────────────────────────────────────────
_RED  = "\033[91m"
_YEL  = "\033[93m"
_RST  = "\033[0m"
_BOLD = "\033[1m"


def _die(msg: str, code: int = 1) -> None:
    print(f"\n{_RED}✗ {msg}{_RST}\n", file=sys.stderr)
    sys.exit(code)


def _warn(msg: str) -> None:
    print(f"{_YEL}⚠ {msg}{_RST}", file=sys.stderr)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cwatch",
        description="Real-time Claude Code usage monitor. Zero dependencies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  cwatch                      live dashboard (refresh every 60s)
  cwatch --interval 30        refresh every 30s
  cwatch --once               one compact line, then exit
  cwatch --json               dump raw API response as JSON
  cwatch --token sk-ant-...   use an explicit token
  CLAUDE_TOKEN=sk-... cwatch  token via env var
        """,
    )
    parser.add_argument("--version", action="version", version=f"cwatch {__version__}")
    parser.add_argument(
        "--interval", "-i",
        type=int, default=60, metavar="SECS",
        help="seconds between refreshes (default: 60, min: 5)",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="print a single compact line and exit",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="dump raw API JSON and exit",
    )
    parser.add_argument(
        "--token", metavar="TOKEN",
        help="Claude Code OAuth access token (overrides auto-detection)",
    )
    parser.add_argument(
        "--creds", metavar="PATH",
        help="path to Claude Code credentials JSON (overrides auto-detection)",
    )
    args = parser.parse_args()

    # ── Resolve token ──────────────────────────────────────────────────────
    token = args.token or get_token(args.creds)
    if not token:
        _die(
            "No Claude Code token found.\n\n"
            "  Make sure you've run:  claude login\n\n"
            "  Or pass it directly:   cwatch --token sk-ant-oat01-...\n"
            "  Or via env var:        CLAUDE_TOKEN=sk-ant-oat01-... cwatch"
        )

    # ── One-shot JSON dump ─────────────────────────────────────────────────
    if args.json:
        try:
            data = fetch(token)
            print(json.dumps(data.raw, indent=2))
        except (AuthError, APIError) as e:
            _die(str(e))
        return

    # ── One-liner mode (tmux / scripting) ─────────────────────────────────
    if args.once:
        try:
            data = fetch(token)
            print(oneliner(data))
        except AuthError as e:
            _die(str(e))
        except APIError as e:
            _warn(str(e))
            print("Claude: error")
        return

    # ── Live dashboard ─────────────────────────────────────────────────────
    interval = max(5, args.interval)
    last_error: str | None = None

    print(f"\n  Starting cwatch (refresh every {interval}s) …\n")
    time.sleep(0.4)

    while True:
        try:
            data = fetch(token)
            last_error = None
            clear_screen()
            print(dashboard(data, datetime.now()))
        except AuthError as e:
            _die(str(e))  # fatal — token won't fix itself
        except APIError as e:
            last_error = str(e)
            clear_screen()
            if last_error:
                print(f"\n  {_YEL}⚠ {last_error}{_RST}\n  Retrying in {interval}s …\n")

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n  Bye!\n")
            break


if __name__ == "__main__":
    main()
