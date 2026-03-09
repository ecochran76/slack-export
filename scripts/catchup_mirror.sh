#!/usr/bin/env bash
set -euo pipefail

# Rate-limit-aware catch-up runner.
# Uses per-channel checkpoints, backs off on Slack 429s, and keeps making progress
# across passes until work is exhausted (or until max passes is reached).

CFG="${1:-config.local.yaml}"
shift $(( $# > 0 ? 1 : 0 )) || true

PY_BIN="./.venv/bin/python"
if [[ ! -x "$PY_BIN" ]]; then
  PY_BIN="python3"
fi

exec "$PY_BIN" scripts/catchup_until_complete.py --config "$CFG" "$@"
