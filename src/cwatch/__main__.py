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
from .api import APIError, AuthError, RateLimitError, fetch
from .credentials import get_token
from .history import save as history_save
from .render import (
    clear_screen,
    cursor_home,
    dashboard,
    oneliner,
    set_terminal_title,
    stats_str,
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

def _ring_bell() -> None:
    sys.stdout.write("\a")
    sys.stdout.flush()


def _interactive_loop(token: str, interval: int, title: bool, bell: bool, plan_override: str = "") -> None:
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
    full_clear   = True
    title_on     = title
    bell_on      = bell
    prev_pct     = -1   # for threshold crossing detection

    try:
        while True:
            # ── Fetch ──────────────────────────────────────────────────────
            if countdown <= 0:
                try:
                    data       = fetch(token)
                    last_error = None
                    countdown  = interval
                    # ── history + bell ────────────────────────────────────
                    if data.five_hour and data.seven_day:
                        history_save(data.five_hour.pct, data.seven_day.pct, data.plan)
                    if bell_on and data.five_hour:
                        new_pct = data.five_hour.pct
                        if (prev_pct < 90 <= new_pct) or (prev_pct < 80 <= new_pct < 90):
                            _ring_bell()
                        prev_pct = new_pct
                except AuthError as e:
                    _restore()
                    _die(str(e))
                except RateLimitError as e:
                    last_error = f"Rate limited — next try in {e.retry_after}s"
                    countdown  = e.retry_after
                except APIError as e:
                    last_error = str(e)
                    countdown  = interval
                full_clear = True

            # ── Build frame ────────────────────────────────────────────────
            if data:
                frame = dashboard(data, datetime.now(), plan_override=plan_override)
                if title_on:
                    set_terminal_title(data)
            else:
                frame = f"\n  {_BOLD}CLAUDE CODE  ·  USAGE MONITOR{_RST}\n\n"

            if last_error:
                frame += f"  {_YEL}⚠  {last_error}{_RST}\n\n"

            frame += status_line(countdown, interval, bell_on=bell_on) + "\n"

            # ── Draw: erase each line before writing to prevent ghosting ───
            if full_clear:
                clear_screen()
                full_clear = False
            else:
                cursor_home()

            # Append \033[K (erase to end of line) after every line
            clean = "\n".join(line + "\033[K" for line in frame.split("\n"))
            sys.stdout.write(clean)
            sys.stdout.write("\033[J")   # erase any remaining lines below
            sys.stdout.flush()

            # ── Wait 1 s, watch for keypresses ─────────────────────────────
            if is_tty:
                ready, _, _ = select.select([sys.stdin], [], [], 1.0)
                if ready:
                    ch = sys.stdin.read(1)
                    if ch in ("q", "Q", "\x03", "\x1b"):
                        break
                    elif ch in ("r", "R"):
                        countdown  = 0
                        full_clear = True
                        continue
                    elif ch == "+":
                        interval = min(300, interval + 5)
                    elif ch == "-":
                        interval = max(5, interval - 5)
                    elif ch in ("t", "T"):
                        title_on = not title_on
                        if not title_on:
                            sys.stdout.write("\033]0;\007")
                            sys.stdout.flush()
                    elif ch in ("b", "B"):
                        bell_on = not bell_on
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
        type=int, default=120, metavar="SECS",
        help="seconds between refreshes (default: 120, min: 5)",
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
        "--plan", choices=["pro", "max5", "max20"], default="", metavar="PLAN",
        help="override plan for token insights: pro, max5, max20 (auto-detected by default)",
    )
    parser.add_argument(
        "--bell", action="store_true",
        help="ring terminal bell when usage crosses 80%% or 90%% (toggle with b key)",
    )
    parser.add_argument(
        "--check", type=int, metavar="PCT",
        help="exit with code 1 if 5-hour usage >= PCT%% (for scripts/CI)",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="show usage history stats and exit",
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

    # ── Stats mode ────────────────────────────────────────────────────────
    if args.stats:
        print(stats_str())
        return

    # ── Check mode (for scripts / CI) ─────────────────────────────────────
    if args.check is not None:
        try:
            data = fetch(token)
            pct  = data.five_hour.pct if data.five_hour else 0
            print(f"Usage: {pct}%  (threshold: {args.check}%)")
            sys.exit(1 if pct >= args.check else 0)
        except (AuthError, APIError) as e:
            _die(str(e))

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
    _interactive_loop(token, max(5, args.interval), title=args.title, bell=args.bell, plan_override=args.plan)


if __name__ == "__main__":
    main()
