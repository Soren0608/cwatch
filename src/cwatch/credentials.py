"""
cwatch.credentials
~~~~~~~~~~~~~~~~~~
Finds the Claude Code OAuth access token across macOS, Linux, and Windows.

Search order:
1. CLAUDE_TOKEN env var (override for CI / API users)
2. macOS Keychain  (security find-generic-password)
3. Linux secret-tool (libsecret)
4. Common credential file paths (~/.claude/.credentials.json, etc.)
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path

_SYSTEM = platform.system()

# Ordered list of file paths to check
_CRED_PATHS = [
    Path.home() / ".claude" / ".credentials.json",
    Path.home() / ".config" / "claude" / "credentials.json",
    Path.home() / "Library" / "Application Support" / "Claude Code" / "credentials.json",
    Path.home() / ".local" / "share" / "claude-code" / "credentials.json",
    Path.home() / "AppData" / "Roaming" / "Claude Code" / "credentials.json",
]

_KEYCHAIN_SERVICE = "Claude Code-credentials"


def _extract_token(data: dict) -> str | None:
    """Pull the access token from a parsed credentials JSON."""
    return (
        data.get("claudeAiOauth", {}).get("accessToken")
        or data.get("accessToken")
        or data.get("token")
    )


def _from_file(path: Path | None = None) -> str | None:
    paths = [path] if path else _CRED_PATHS
    for p in paths:
        if p and p.exists():
            try:
                return _extract_token(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass
    return None


def _from_keychain() -> str | None:
    if _SYSTEM == "Darwin":
        try:
            raw = subprocess.check_output(
                ["security", "find-generic-password", "-s", _KEYCHAIN_SERVICE, "-w"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode().strip()
            return _extract_token(json.loads(raw))
        except Exception:
            pass

    if _SYSTEM == "Linux":
        try:
            out = subprocess.check_output(
                ["secret-tool", "lookup", "service", _KEYCHAIN_SERVICE],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode().strip()
            # secret-tool may return raw token or JSON
            try:
                return _extract_token(json.loads(out))
            except json.JSONDecodeError:
                return out or None
        except Exception:
            pass

    return None


def get_token(custom_path: str | None = None) -> str | None:
    """
    Return the Claude Code access token, or None if not found.

    Args:
        custom_path: Optional explicit path to the credentials JSON file.
    """
    # 1. Env var override (useful for API users or CI)
    env = os.environ.get("CLAUDE_TOKEN", "").strip()
    if env:
        return env

    # 2. Platform keychain
    token = _from_keychain()
    if token:
        return token

    # 3. File system
    path = Path(custom_path) if custom_path else None
    return _from_file(path)
