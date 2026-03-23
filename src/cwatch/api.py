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

_USAGE_URL  = "https://api.anthropic.com/api/oauth/usage"
_USER_AGENT = "claude-code/2.0.31"
_BETA_HEADER = "oauth-2025-04-20"
_TIMEOUT = 10

FIVE_HOUR_SECS  = 5 * 3600        # 18 000
SEVEN_DAY_SECS  = 7 * 24 * 3600   # 604 800


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
        m, s   = divmod(rem, 60)
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"

    def elapsed_pct(self, total_seconds: int) -> Optional[int]:
        """Percentage of the window period already elapsed."""
        secs = self.seconds_until_reset
        if secs is None:
            return None
        elapsed = max(0, total_seconds - secs)
        return min(100, round(elapsed / total_seconds * 100))

    def eta_str(self, total_seconds: int) -> Optional[str]:
        """
        Estimated time until 100% utilisation at the current burn rate.
        Returns None if not enough data (< 5 min elapsed, rate ≈ 0, already at limit).
        """
        secs = self.seconds_until_reset
        if secs is None:
            return None
        elapsed = max(0, total_seconds - secs)
        if elapsed < 300 or self.utilization <= 0:   # need ≥ 5 min of history
            return None
        if self.utilization >= 100:
            return "now"
        rate_per_sec = self.utilization / elapsed     # % per second
        secs_left = (100 - self.utilization) / rate_per_sec
        h, rem = divmod(int(secs_left), 3600)
        m      = rem // 60
        if h >= 24:
            return f"~{h // 24}d"
        if h:
            return f"~{h}h {m}m"
        return f"~{m}m"


@dataclass
class UsageData:
    five_hour:      Optional[Window]
    seven_day:      Optional[Window]
    seven_day_opus: Optional[Window]
    raw: dict

    @property
    def plan(self) -> str:
        """
        Infer plan from API response.
        Prefer an explicit field in the raw payload; fall back to heuristics.
        """
        explicit = self.raw.get("plan") or self.raw.get("subscription_plan")
        if explicit:
            return str(explicit).title()
        # Opus window only exists on Max plans
        if self.seven_day_opus and self.seven_day_opus.utilization > 0:
            return "Max"
        return "Pro"


class AuthError(Exception):
    """Token is missing or rejected by the API."""


class APIError(Exception):
    """Non-auth API error."""


class RateLimitError(APIError):
    """HTTP 429 — too many requests."""
    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"Rate limited — retry in {retry_after}s")


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
        APIError:  on other HTTP errors or network issues
    """
    req = urllib.request.Request(
        _USAGE_URL,
        headers={
            "Accept":           "application/json",
            "Content-Type":     "application/json",
            "User-Agent":       _USER_AGENT,
            "Authorization":    f"Bearer {token}",
            "anthropic-beta":   _BETA_HEADER,
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
        if e.code == 429:
            retry_after = int(e.headers.get("Retry-After", 60))
            raise RateLimitError(retry_after) from e
        raise APIError(f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise APIError(f"Network error: {e.reason}") from e

    return UsageData(
        five_hour=     _parse_window(raw.get("five_hour")),
        seven_day=     _parse_window(raw.get("seven_day")),
        seven_day_opus=_parse_window(raw.get("seven_day_opus")),
        raw=raw,
    )
