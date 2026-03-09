#!/usr/bin/env bash
set -euo pipefail

# One-command status and health snapshot for a single-workspace live stack.
#
# Usage:
#   scripts/live_mode_status.sh [workspace]
# Example:
#   scripts/live_mode_status.sh default

WORKSPACE="${1:-default}"
DB_PATH="./.local/state/slack_mirror_test.db"

UNITS=(
  "slack-mirror-webhooks-${WORKSPACE}.service"
  "slack-mirror-events-${WORKSPACE}.service"
  "slack-mirror-embeddings-${WORKSPACE}.service"
)

echo "== systemd user service status =="
systemctl --user --no-pager --full status "${UNITS[@]}" 2>/dev/null | sed -n '1,120p' || true

echo

echo "== socket mode note =="
echo "No HTTP health endpoint in Socket Mode; rely on service status and DB freshness."

echo

echo "== latest mirrored message =="
if [[ -f "${DB_PATH}" ]]; then
  sqlite3 "${DB_PATH}" "select w.name, datetime(max(CAST(m.ts as real)), 'unixepoch', 'localtime') from messages m join workspaces w on w.id=m.workspace_id where w.name='${WORKSPACE}' group by w.name;" || true
else
  echo "db not found: ${DB_PATH}"
fi

echo

echo "== events queue counts =="
if [[ -f "${DB_PATH}" ]]; then
  sqlite3 "${DB_PATH}" "select status, count(*) from events e join workspaces w on w.id=e.workspace_id where w.name='${WORKSPACE}' group by status order by status;" || true
else
  echo "db not found: ${DB_PATH}"
fi

echo

echo "== embedding jobs counts =="
if [[ -f "${DB_PATH}" ]]; then
  sqlite3 "${DB_PATH}" "select status, count(*) from embedding_jobs j join workspaces w on w.id=j.workspace_id where w.name='${WORKSPACE}' group by status order by status;" || true
else
  echo "db not found: ${DB_PATH}"
fi
