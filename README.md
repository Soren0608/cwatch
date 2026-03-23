# cwatch

**Real-time Claude Code usage monitor. Zero dependencies.**

```
pip install cwatch
cwatch
```

```
──────────────────────────────────────────────────────────
  CLAUDE CODE  ·  USAGE MONITOR
──────────────────────────────────────────────────────────

  5-hour session
  [████████████░░░░░░░░░░░░░]   48%  reset in 2h 31m (18:00:00)

  7-day window
  [████░░░░░░░░░░░░░░░░░░░░░]   18%  reset in 4d 12h (Sat 00:00)

──────────────────────────────────────────────────────────
  Updated 15:28:43   ·   Ctrl+C to exit
```

## Why cwatch?

| | cwatch | claude-monitor |
|---|---|---|
| Dependencies | **zero** (stdlib only) | Rich, Pydantic, pytz… |
| Data source | **live OAuth API** | local JSONL files |
| Install | `pip install cwatch` | requires ccusage (npm) + pip |
| Python | 3.9+ | 3.9+ |

`cwatch` reads the same internal API endpoint that Claude Code itself uses — numbers are exact and real-time, no token-counting heuristics.

## Install

```bash
pip install cwatch
# or isolated (recommended)
pipx install cwatch
uv tool install cwatch
```

Requires: Python 3.9+ and having run `claude login` at least once.

## Usage

```bash
cwatch                        # live dashboard, refresh every 60s
cwatch --interval 30          # faster refresh
cwatch --once                 # one compact line, then exit
cwatch --json                 # raw API JSON dump
cwatch --token sk-ant-oat01-… # explicit token
CLAUDE_TOKEN=sk-… cwatch      # token via env var
```

### tmux statusline

```tmux
set -g status-right "#(cwatch --once)  %H:%M"
set -g status-interval 60
```

## How it works

Calls `GET https://api.anthropic.com/api/oauth/usage` with your Claude Code
OAuth token (read from macOS Keychain, `~/.claude/.credentials.json`, or
`CLAUDE_TOKEN` env var).

## Python API

```python
from cwatch.credentials import get_token
from cwatch.api import fetch

data = fetch(get_token())
print(f"5h session: {data.five_hour.pct}%  resets in {data.five_hour.time_until_reset}")
```

## Contributing

PRs welcome. Please keep the zero-dependencies constraint.

```bash
git clone https://github.com/YOUR_USER/cwatch && cd cwatch
pip install -e . && pytest
```

## License

MIT © 2026
