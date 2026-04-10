#!/usr/bin/env bash
set -euo pipefail

# One-shot status for both workspace live stacks.
# Usage: scripts/live_mode_status_all.sh

DB_PATH="${SLACK_MIRROR_DB_PATH:-$HOME/.local/state/slack-mirror/slack_mirror.db}"

UNITS=(
  slack-mirror-webhooks-default.service
  slack-mirror-daemon-default.service
  slack-mirror-webhooks-soylei.service
  slack-mirror-daemon-soylei.service
)

LEGACY_UNITS=(
  slack-mirror-events-default.service
  slack-mirror-embeddings-default.service
  slack-mirror-events-soylei.service
  slack-mirror-embeddings-soylei.service
)

echo "== systemd user services =="
systemctl --user --no-pager --full status "${UNITS[@]}" 2>/dev/null | sed -n '1,220p' || true

echo
echo "== duplicate topology check =="
for unit in "${LEGACY_UNITS[@]}"; do
  active="$(systemctl --user is-active "${unit}" 2>/dev/null || true)"
  if [[ "${active}" == "active" ]]; then
    echo "duplicate_topology: ${unit} is active"
  fi
done

echo
if [[ -f "${DB_PATH}" ]]; then
  run_query() {
    local sql="$1"
    python3 - "$DB_PATH" "$sql" <<'PY'
import sqlite3
import sys

db_path = sys.argv[1]
sql = sys.argv[2]
conn = sqlite3.connect(db_path, timeout=10)
for row in conn.execute(sql):
    print("|".join("" if value is None else str(value) for value in row))
PY
  }

  echo "== latest mirrored messages by workspace =="
  run_query "select w.name, datetime(max(CAST(m.ts as real)), 'unixepoch', 'localtime') from messages m join workspaces w on w.id=m.workspace_id group by w.name order by w.name;" || true

  echo
  echo "== events by workspace/status =="
  run_query "select w.name, e.status, count(*) from events e join workspaces w on w.id=e.workspace_id group by w.name,e.status order by w.name,e.status;" || true

  echo
  echo "== embedding_jobs by workspace/status =="
  run_query "select w.name, j.status, count(*) from embedding_jobs j join workspaces w on w.id=j.workspace_id group by w.name,j.status order by w.name,j.status;" || true
else
  echo "DB not found: ${DB_PATH}"
fi
