"""
cwatch.render
~~~~~~~~~~~~~
Terminal rendering: ANSI bars, colors, full-screen dashboard, one-liner.
All display logic lives here — clean separation from fetch/parse logic.
"""

from __future__ import annotations

import os
import platform
from datetime import datetime
from typing import Optional

from .api import UsageData, Window

# ─── ANSI codes ───────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
WHITE  = "\033[97m"


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
    return GREEN


def bar(pct: int, width: int = 25, colored: bool = True) -> str:
    """Return a filled progress bar string."""
    filled = round(pct / 100 * width)
    empty = width - filled
    fill_char = "█"
    empty_char = "░"
    if colored and not _NO_COLOR:
        c = _color_for(pct)
        return f"{c}{fill_char * filled}{RESET}{DIM}{empty_char * empty}{RESET}"
    return fill_char * filled + empty_char * empty


def _window_lines(label: str, w: Optional[Window], bar_width: int = 25) -> list[str]:
    if w is None:
        return [f"  {_c(DIM, label + ':'):22s}  {_c(DIM, 'no data')}"]

    pct = w.pct
    b = bar(pct, bar_width)
    c = _color_for(pct)
    reset_str = w.time_until_reset
    reset_at = ""
    if w.resets_at:
        reset_at = w.resets_at.astimezone().strftime("%H:%M:%S")

    lines = [
        f"  {_c(BOLD, label)}",
        f"  [{b}]  {_c(c, f'{pct:3d}%')}  {_c(DIM, f'reset in {reset_str}  ({reset_at})')}",
    ]
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
        b = bar(pct, 10)
        parts.append(f"Claude [{b}] {pct}%")
    if data.seven_day:
        parts.append(f"7d:{data.seven_day.pct}%")
    return "  ".join(parts) if parts else "Claude: no data"


def dashboard(data: UsageData, updated_at: Optional[datetime] = None) -> str:
    """Full-screen dashboard string."""
    sep = _c(CYAN, "─" * 58)
    lines: list[str] = [
        "",
        sep,
        f"  {_c(BOLD + CYAN, 'CLAUDE CODE  ·  USAGE MONITOR')}",
        sep,
        "",
    ]

    lines += _window_lines("5-hour session", data.five_hour)
    lines += [""]
    lines += _window_lines("7-day window  ", data.seven_day)

    if data.seven_day_opus and data.seven_day_opus.utilization > 0:
        lines += [""]
        lines += _window_lines("Opus (weekly) ", data.seven_day_opus)

    lines += ["", sep]

    ts = (updated_at or datetime.now()).strftime("%H:%M:%S")
    lines.append(f"  {_c(DIM, f'Updated {ts}   ·   Ctrl+C to exit')}")
    lines.append("")

    return "\n".join(lines)


def clear_screen() -> None:
    os.system("cls" if platform.system() == "Windows" else "clear")
