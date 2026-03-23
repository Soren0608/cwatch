"""
cwatch.api
~~~~~~~~~~
Fetches usage data from Anthropic's internal OAuth usage endpoint.
No third-party dependencies — uses only stdlib urllib.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
_USER_AGENT = "claude-code/2.0.31"
_BETA_HEADER = "oauth-2025-04-20"
_TIMEOUT = 10


@dataclass
class Window:
    """One usage window (5-hour session or 7-day week)."""
    utilization: float          # 0.0 – 100.0
    resets_at: Optional[datetime]

    @property
    def pct(self) -> int:
        return min(100, max(0, round(self.utilization)))

    @property
    def seconds_until_reset(self) -> Optional[int]:
        if self.resets_at is None:
            return None
        delta = self.resets_at - datetime.now(tz=timezone.utc)
        return max(0, int(delta.total_seconds()))

    @property
    def time_until_reset(self) -> str:
        secs = self.seconds_until_reset
        if secs is None:
            return "unknown"
        if secs == 0:
            return "now"
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"


@dataclass
class UsageData:
    five_hour: Optional[Window]
    seven_day: Optional[Window]
    seven_day_opus: Optional[Window]
    raw: dict


class AuthError(Exception):
    """Token is missing or rejected by the API."""


class APIError(Exception):
    """Non-auth API error."""


def _parse_window(obj: dict | None) -> Optional[Window]:
    if not obj:
        return None
    resets_at = None
    if obj.get("resets_at"):
        try:
            resets_at = datetime.fromisoformat(
                obj["resets_at"].replace("Z", "+00:00")
            )
        except Exception:
            pass
    return Window(
        utilization=float(obj.get("utilization", 0.0)),
        resets_at=resets_at,
    )


def fetch(token: str) -> UsageData:
    """
    Fetch usage data from Anthropic.

    Raises:
        AuthError: on 401/403
        APIError: on other HTTP errors or network issues
    """
    req = urllib.request.Request(
        _USAGE_URL,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
            "Authorization": f"Bearer {token}",
            "anthropic-beta": _BETA_HEADER,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise AuthError(
                f"Token rejected (HTTP {e.code}). Try running: claude login"
            ) from e
        raise APIError(f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise APIError(f"Network error: {e.reason}") from e

    return UsageData(
        five_hour=_parse_window(raw.get("five_hour")),
        seven_day=_parse_window(raw.get("seven_day")),
        seven_day_opus=_parse_window(raw.get("seven_day_opus")),
        raw=raw,
    )
