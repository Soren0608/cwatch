"""Tests for cwatch — runs with plain `pytest` or `python -m pytest`."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from cwatch.api import Window, UsageData, _parse_window, fetch, AuthError, APIError
from cwatch.render import bar, oneliner, dashboard
from cwatch.credentials import _extract_token


# ─── credentials ──────────────────────────────────────────────────────────────

def test_extract_token_nested():
    data = {"claudeAiOauth": {"accessToken": "sk-ant-test"}}
    assert _extract_token(data) == "sk-ant-test"


def test_extract_token_flat():
    data = {"accessToken": "sk-ant-flat"}
    assert _extract_token(data) == "sk-ant-flat"


def test_extract_token_missing():
    assert _extract_token({}) is None


# ─── api.Window ───────────────────────────────────────────────────────────────

def test_window_pct_clamp():
    w = Window(utilization=105.0, resets_at=None)
    assert w.pct == 100

    w2 = Window(utilization=-5.0, resets_at=None)
    assert w2.pct == 0


def test_window_time_until_reset():
    future = datetime.now(tz=timezone.utc) + timedelta(hours=2, minutes=30)
    w = Window(utilization=50.0, resets_at=future)
    assert "2h" in w.time_until_reset
    assert "m" in w.time_until_reset  # some minutes shown


def test_window_time_until_reset_none():
    w = Window(utilization=50.0, resets_at=None)
    assert w.time_until_reset == "unknown"


def test_window_time_past_reset():
    past = datetime.now(tz=timezone.utc) - timedelta(seconds=10)
    w = Window(utilization=100.0, resets_at=past)
    assert w.time_until_reset == "now"
    assert w.seconds_until_reset == 0


def test_parse_window_none():
    assert _parse_window(None) is None
    # empty dict has no utilization key — still returns None (treated as no data)


def test_parse_window_full():
    obj = {"utilization": 42.5, "resets_at": "2026-03-23T18:00:00Z"}
    w = _parse_window(obj)
    assert w is not None
    assert w.pct == 42  # round(42.5) == 42 in Python (banker's rounding)
    assert w.resets_at is not None


# ─── render.bar ───────────────────────────────────────────────────────────────

def test_bar_zero():
    result = bar(0, width=10, colored=False)
    assert result == "░" * 10


def test_bar_full():
    result = bar(100, width=10, colored=False)
    assert result == "█" * 10


def test_bar_half():
    result = bar(50, width=10, colored=False)
    assert result == "█████░░░░░"


def test_bar_width():
    result = bar(75, width=20, colored=False)
    assert len(result) == 20


# ─── render.oneliner ──────────────────────────────────────────────────────────

def _make_data(pct5: float = 40.0, pct7: float = 20.0) -> UsageData:
    future = datetime.now(tz=timezone.utc) + timedelta(hours=3)
    return UsageData(
        five_hour=Window(utilization=pct5, resets_at=future),
        seven_day=Window(utilization=pct7, resets_at=future),
        seven_day_opus=None,
        raw={},
    )


def test_oneliner_contains_pct():
    data = _make_data(40.0, 20.0)
    line = oneliner(data)
    assert "40%" in line
    assert "7d:20%" in line


def test_oneliner_no_data():
    data = UsageData(five_hour=None, seven_day=None, seven_day_opus=None, raw={})
    assert "no data" in oneliner(data)


# ─── render.dashboard ────────────────────────────────────────────────────────

def test_dashboard_contains_labels():
    data = _make_data(55.0, 30.0)
    out = dashboard(data)
    assert "5-hour" in out
    assert "7-day" in out
    assert "55%" in out
    assert "30%" in out


def test_dashboard_opus_hidden_when_zero():
    future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    data = UsageData(
        five_hour=Window(utilization=50.0, resets_at=future),
        seven_day=Window(utilization=20.0, resets_at=future),
        seven_day_opus=Window(utilization=0.0, resets_at=None),
        raw={},
    )
    out = dashboard(data)
    assert "Opus" not in out


def test_dashboard_opus_shown_when_nonzero():
    future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    data = UsageData(
        five_hour=Window(utilization=50.0, resets_at=future),
        seven_day=Window(utilization=20.0, resets_at=future),
        seven_day_opus=Window(utilization=15.0, resets_at=future),
        raw={},
    )
    out = dashboard(data)
    assert "Opus" in out


# ─── api.fetch (mocked) ───────────────────────────────────────────────────────

def test_fetch_success():
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"five_hour": {"utilization": 35.0, "resets_at": null}, "seven_day": null}'
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        data = fetch("fake-token")

    assert data.five_hour is not None
    assert data.five_hour.pct == 35
    assert data.seven_day is None


def test_fetch_auth_error():
    import urllib.error
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
        url="", code=401, msg="Unauthorized", hdrs=None, fp=None
    )):
        with pytest.raises(AuthError):
            fetch("bad-token")


def test_fetch_network_error():
    import urllib.error
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
        with pytest.raises(APIError):
            fetch("token")
