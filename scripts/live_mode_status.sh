#!/usr/bin/env bash
set -euo pipefail

# One-command status and health snapshot for live mode.
#
# Usage:
#   scripts/live_mode_status.sh [port]
# Example:
#   scripts/live_mode_status.sh 8787

PORT="${1:-8787}"
DB_PATH="cache/slack_mirror.db"

UNITS=(
  "slack-mirror-webhooks.service"
  "slack-mirror-events.service"
  "slack-mirror-embeddings.service"
)

echo "== systemd user service status =="
systemctl --user --no-pager --full status "${UNITS[@]}" 2>/dev/null | sed -n '1,80p' || true

echo

echo "== webhook healthz =="
if curl -fsS "http://127.0.0.1:${PORT}/healthz"; then
  echo
else
  echo "healthz check failed on port ${PORT}" >&2
fi

echo

echo "== events queue counts =="
if [[ -f "${DB_PATH}" ]]; then
  sqlite3 "${DB_PATH}" "select status, count(*) from events group by status order by status;" || true
else
  echo "db not found: ${DB_PATH}"
fi

echo

echo "== embedding jobs counts =="
if [[ -f "${DB_PATH}" ]]; then
  sqlite3 "${DB_PATH}" "select status, count(*) from embedding_jobs group by status order by status;" || true
else
  echo "db not found: ${DB_PATH}"
fi
