#!/usr/bin/env bash
set -euo pipefail

# One-command status and health snapshot for a single-workspace live stack.
#
# Usage:
#   scripts/live_mode_status.sh [workspace]
# Example:
#   scripts/live_mode_status.sh default

WORKSPACE="${1:-default}"
DB_PATH="${SLACK_MIRROR_DB_PATH:-$HOME/.local/state/slack-mirror/slack_mirror.db}"

UNITS=(
  "slack-mirror-webhooks-${WORKSPACE}.service"
  "slack-mirror-daemon-${WORKSPACE}.service"
)

LEGACY_UNITS=(
  "slack-mirror-events-${WORKSPACE}.service"
  "slack-mirror-embeddings-${WORKSPACE}.service"
)

echo "== systemd user service status =="
systemctl --user --no-pager --full status "${UNITS[@]}" 2>/dev/null | sed -n '1,120p' || true

echo

echo "== topology check =="
for unit in "${LEGACY_UNITS[@]}"; do
  active="$(systemctl --user is-active "${unit}" 2>/dev/null || true)"
  if [[ "${active}" == "active" ]]; then
    echo "duplicate_topology: ${unit} is active"
  fi
done
for unit in "${UNITS[@]}"; do
  echo "${unit}: $(systemctl --user is-active "${unit}" 2>/dev/null || true)"
done

echo

echo "== socket mode note =="
echo "No HTTP health endpoint in Socket Mode; rely on service status and DB freshness."

echo

echo "== latest mirrored message =="
if [[ -f "${DB_PATH}" ]]; then
  python3 - "${DB_PATH}" "${WORKSPACE}" <<'PY'
import sqlite3
import sys

db_path = sys.argv[1]
workspace = sys.argv[2]
conn = sqlite3.connect(db_path, timeout=10)
sql = "select w.name, datetime(max(CAST(m.ts as real)), 'unixepoch', 'localtime') from messages m join workspaces w on w.id=m.workspace_id where w.name=? group by w.name;"
for row in conn.execute(sql, (workspace,)):
    print("|".join("" if value is None else str(value) for value in row))
PY
else
  echo "db not found: ${DB_PATH}"
fi

echo

echo "== events queue counts =="
if [[ -f "${DB_PATH}" ]]; then
  python3 - "${DB_PATH}" "${WORKSPACE}" <<'PY'
import sqlite3
import sys

db_path = sys.argv[1]
workspace = sys.argv[2]
conn = sqlite3.connect(db_path, timeout=10)
sql = "select status, count(*) from events e join workspaces w on w.id=e.workspace_id where w.name=? group by status order by status;"
for row in conn.execute(sql, (workspace,)):
    print("|".join("" if value is None else str(value) for value in row))
PY
else
  echo "db not found: ${DB_PATH}"
fi

echo

echo "== embedding jobs counts =="
if [[ -f "${DB_PATH}" ]]; then
  python3 - "${DB_PATH}" "${WORKSPACE}" <<'PY'
import sqlite3
import sys

db_path = sys.argv[1]
workspace = sys.argv[2]
conn = sqlite3.connect(db_path, timeout=10)
sql = "select status, count(*) from embedding_jobs j join workspaces w on w.id=j.workspace_id where w.name=? group by status order by status;"
for row in conn.execute(sql, (workspace,)):
    print("|".join("" if value is None else str(value) for value in row))
PY
else
  echo "db not found: ${DB_PATH}"
fi
