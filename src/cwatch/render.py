"""
cwatch.render
~~~~~~~~~~~~~
Terminal rendering: ANSI bars, colors, full-screen dashboard, one-liner.
All display logic lives here — clean separation from fetch/parse logic.
"""

from __future__ import annotations

import os
import platform
import sys
from datetime import datetime
from typing import Optional

from .api import FIVE_HOUR_SECS, SEVEN_DAY_SECS, UsageData, Window

# ─── ANSI codes ───────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
WHITE  = "\033[97m"
BLUE   = "\033[94m"


def sys_supports_color() -> bool:
    if platform.system() == "Windows":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32  # type: ignore
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return True


_NO_COLOR = os.environ.get("NO_COLOR") or not sys_supports_color()


def _c(code: str, text: str) -> str:
    if _NO_COLOR:
        return text
    return f"{code}{text}{RESET}"


# ─── Building blocks ──────────────────────────────────────────────────────────

def _color_for(pct: int) -> str:
    if pct >= 90:
        return RED
    if pct >= 75:
        return YELLOW
    if pct >= 50:
        return CYAN
    return GREEN


def bar(pct: int, width: int = 25, colored: bool = True, color: Optional[str] = None) -> str:
    """Return a filled progress bar string."""
    filled     = round(pct / 100 * width)
    empty      = width - filled
    fill_char  = "█"
    empty_char = "░"
    if colored and not _NO_COLOR:
        c = color or _color_for(pct)
        return f"{c}{fill_char * filled}{RESET}{DIM}{empty_char * empty}{RESET}"
    return fill_char * filled + empty_char * empty


def _window_block(
    label: str,
    w: Optional[Window],
    total_seconds: int,
    bar_width: int = 25,
    show_eta: bool = False,
) -> list[str]:
    """Return lines for one usage window (usage bar + time bar)."""
    if w is None:
        return [f"  {_c(DIM, label + ':'):22s}  {_c(DIM, 'no data')}"]

    pct     = w.pct
    b_usage = bar(pct, bar_width)
    c       = _color_for(pct)

    if w.resets_at:
        reset_at   = w.resets_at.astimezone().strftime("%H:%M:%S")
        reset_info = f"reset in {w.time_until_reset}  ({reset_at})"
    else:
        reset_info = "reset time pending"

    # ── usage line ────────────────────────────────────────────────────────────
    usage_line = (
        f"  [{b_usage}]  {_c(c, f'{pct:3d}%')}  "
        f"{_c(DIM, reset_info)}"
    )

    # ── time bar line ─────────────────────────────────────────────────────────
    elapsed = w.elapsed_pct(total_seconds)
    time_line = ""
    if elapsed is not None:
        b_time = bar(elapsed, bar_width, colored=True, color=BLUE)
        eta_part = ""
        if show_eta:
            eta = w.eta_str(total_seconds)
            if eta:
                eta_part = f"  {_c(YELLOW, f'limit in {eta} at this rate')}"
        time_line = (
            f"  [{b_time}]  {_c(DIM, f'{elapsed:3d}%')}"
            f"  {_c(DIM, 'time elapsed')}{eta_part}"
        )

    lines = [f"  {_c(BOLD, label)}", usage_line]
    if time_line:
        lines.append(time_line)
    return lines


# ─── Output modes ─────────────────────────────────────────────────────────────

def oneliner(data: UsageData) -> str:
    """
    Compact single line — good for tmux statusline or scripting.
    Example:  Claude [████████░░░░░░░░░░░░░░░░░] 32%  7d:18%
    """
    parts = []
    if data.five_hour:
        pct = data.five_hour.pct
        b   = bar(pct, 10)
        parts.append(f"Claude [{b}] {pct}%")
    if data.seven_day:
        parts.append(f"7d:{data.seven_day.pct}%")
    return "  ".join(parts) if parts else "Claude: no data"


def dashboard(data: UsageData, updated_at: Optional[datetime] = None) -> str:
    """Full-screen dashboard string."""
    sep   = _c(CYAN, "─" * 60)
    plan  = _c(BOLD, data.plan)
    title = _c(BOLD + CYAN, "CLAUDE CODE  ·  USAGE MONITOR")

    lines: list[str] = [
        "",
        sep,
        f"  {title:<40s}  {plan}",
        sep,
        "",
    ]

    lines += _window_block("5-hour session", data.five_hour,  FIVE_HOUR_SECS, show_eta=True)
    lines += [""]
    lines += _window_block("7-day window  ", data.seven_day,  SEVEN_DAY_SECS)

    if data.seven_day_opus and data.seven_day_opus.utilization > 0:
        lines += [""]
        lines += _window_block("Opus (weekly) ", data.seven_day_opus, SEVEN_DAY_SECS)

    lines += ["", sep]

    ts = (updated_at or datetime.now()).strftime("%H:%M:%S")
    lines.append(f"  {_c(DIM, f'Updated {ts}')}")
    lines.append("")

    return "\n".join(lines)


def status_line(countdown: int, interval: int) -> str:
    """Updatable one-line status bar shown below the dashboard."""
    keys  = "[r] refresh  [+/-] interval  [t] title  [q] quit"
    timer = f"Next refresh in {countdown}s  (every {interval}s)"
    return f"  {_c(DIM, timer + '   ·   ' + keys)}"


def set_terminal_title(data: UsageData) -> None:
    """Update the terminal window/tab title with current usage."""
    parts = []
    if data.five_hour:
        parts.append(f"5h:{data.five_hour.pct}%")
    if data.seven_day:
        parts.append(f"7d:{data.seven_day.pct}%")
    title = "Claude " + "  ".join(parts) if parts else "Claude"
    sys.stdout.write(f"\033]0;{title}\007")
    sys.stdout.flush()


def clear_screen() -> None:
    """Full clear — only on first draw or forced refresh."""
    if platform.system() == "Windows":
        os.system("cls")
    else:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


def cursor_home() -> None:
    """Move cursor to top-left without erasing — for tick redraws (no flicker)."""
    if platform.system() == "Windows":
        os.system("cls")
    else:
        sys.stdout.write("\033[H")
        sys.stdout.flush()
