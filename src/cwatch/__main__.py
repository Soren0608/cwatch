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
  cwatch --title              # update terminal title bar with usage %
  cwatch --token sk-ant-...   # pass token explicitly
  cwatch --creds ~/path.json  # custom credentials file

Keys (live mode)
----------------
  r / R   force refresh now
  +       increase interval by 5s
  -       decrease interval by 5s
  t       toggle terminal title updates
  q / Q   quit
  Ctrl+C  quit
"""

from __future__ import annotations

import argparse
import json
import select
import sys
import time
from datetime import datetime

from . import __version__
from .api import APIError, AuthError, fetch
from .credentials import get_token
from .render import (
    clear_screen,
    dashboard,
    oneliner,
    rewrite_status,
    set_terminal_title,
    status_line,
)

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


# ─── Interactive live loop ────────────────────────────────────────────────────

def _interactive_loop(token: str, interval: int, title: bool) -> None:
    is_tty       = sys.stdin.isatty()
    old_settings = None

    if is_tty:
        import termios, tty  # noqa – stdlib, always available on Unix/macOS
        old_settings = termios.tcgetattr(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())

    def _restore() -> None:
        if old_settings is not None:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)

    countdown    = 0
    data         = None
    last_error:  str | None = None
    needs_redraw = True
    title_on     = title

    try:
        while True:
            # ── Fetch ──────────────────────────────────────────────────────
            if countdown <= 0:
                try:
                    data       = fetch(token)
                    last_error = None
                except AuthError as e:
                    _restore()
                    _die(str(e))
                except APIError as e:
                    last_error = str(e)
                countdown    = interval
                needs_redraw = True

            # ── Draw ───────────────────────────────────────────────────────
            if needs_redraw:
                clear_screen()
                if data:
                    sys.stdout.write(dashboard(data, datetime.now()))
                    if title_on:
                        set_terminal_title(data)
                if last_error:
                    sys.stdout.write(f"\n  {_YEL}⚠ {last_error}{_RST}\n")
                sys.stdout.write(status_line(countdown, interval) + "\n")
                sys.stdout.flush()
                needs_redraw = False
            else:
                rewrite_status(status_line(countdown, interval))

            # ── Wait 1 s, watch for keypresses ─────────────────────────────
            if is_tty:
                ready, _, _ = select.select([sys.stdin], [], [], 1.0)
                if ready:
                    ch = sys.stdin.read(1)
                    if ch in ("q", "Q", "\x03", "\x1b"):
                        break
                    elif ch in ("r", "R"):
                        countdown    = 0
                        needs_redraw = True
                        continue
                    elif ch == "+":
                        interval = min(300, interval + 5)
                    elif ch == "-":
                        interval = max(5, interval - 5)
                    elif ch in ("t", "T"):
                        title_on = not title_on
                        if not title_on:
                            sys.stdout.write("\033]0;\007")  # clear title
                            sys.stdout.flush()
            else:
                time.sleep(1)

            countdown -= 1

    except KeyboardInterrupt:
        pass
    finally:
        _restore()
        # Reset terminal title on exit
        sys.stdout.write("\033]0;\007")
        sys.stdout.write("\n\n  Bye!\n\n")
        sys.stdout.flush()


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
  cwatch --title              update terminal title bar with usage %%
  cwatch --token sk-ant-...   use an explicit token
  CLAUDE_TOKEN=sk-... cwatch  token via env var

keys (live mode):
  r / R   refresh now
  + / -   adjust interval (±5s)
  t       toggle terminal title updates
  q       quit
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
        "--title", action="store_true",
        help="update terminal title bar with usage %%",
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

    # ── Interactive live dashboard ─────────────────────────────────────────
    _interactive_loop(token, max(5, args.interval), title=args.title)


if __name__ == "__main__":
    main()
