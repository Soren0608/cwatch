"""
cwatch.history
~~~~~~~~~~~~~~
Persists usage readings to ~/.cwatch/history.json and generates stats.
Zero dependencies — pure stdlib.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

_HISTORY_FILE = Path.home() / ".cwatch" / "history.json"
_MAX_ENTRIES  = 1000


# ─── Write ────────────────────────────────────────────────────────────────────

def save(five_hour_pct: int, seven_day_pct: int, plan: str) -> None:
    """Append a reading to the history file. Silent on errors."""
    try:
        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {"entries": []}

        data.setdefault("entries", []).append({
            "ts":            datetime.now().isoformat(timespec="seconds"),
            "five_hour_pct": five_hour_pct,
            "seven_day_pct": seven_day_pct,
            "plan":          plan,
        })
        data["entries"] = data["entries"][-_MAX_ENTRIES:]
        _HISTORY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


# ─── Read / stats ─────────────────────────────────────────────────────────────

def _load() -> list[dict]:
    try:
        return json.loads(_HISTORY_FILE.read_text(encoding="utf-8")).get("entries", [])
    except Exception:
        return []


def stats() -> dict:
    """
    Return a dict with pre-computed stats.
    Keys: total, avg_pct, peak_pct, times_80, times_90,
          today_avg, today_peak, yesterday_avg, peak_hour
    """
    entries = _load()
    if not entries:
        return {}

    now       = datetime.now()
    today     = now.date()
    yesterday = (now - timedelta(days=1)).date()

    all_pcts       = [e["five_hour_pct"] for e in entries]
    today_pcts     = [e["five_hour_pct"] for e in entries
                      if datetime.fromisoformat(e["ts"]).date() == today]
    yesterday_pcts = [e["five_hour_pct"] for e in entries
                      if datetime.fromisoformat(e["ts"]).date() == yesterday]

    # peak hour (most activity)
    hour_counts: dict[int, int] = {}
    for e in entries:
        h = datetime.fromisoformat(e["ts"]).hour
        hour_counts[h] = hour_counts.get(h, 0) + 1
    peak_hour = max(hour_counts, key=lambda h: hour_counts[h]) if hour_counts else None

    def _avg(lst: list[int]) -> int:
        return round(sum(lst) / len(lst)) if lst else 0

    return {
        "total":          len(entries),
        "avg_pct":        _avg(all_pcts),
        "peak_pct":       max(all_pcts),
        "times_80":       sum(1 for p in all_pcts if p >= 80),
        "times_90":       sum(1 for p in all_pcts if p >= 90),
        "today_avg":      _avg(today_pcts),
        "today_peak":     max(today_pcts) if today_pcts else 0,
        "today_count":    len(today_pcts),
        "yesterday_avg":  _avg(yesterday_pcts),
        "yesterday_peak": max(yesterday_pcts) if yesterday_pcts else 0,
        "peak_hour":      peak_hour,
    }
