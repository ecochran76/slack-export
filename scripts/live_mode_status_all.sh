#!/usr/bin/env bash
set -euo pipefail

# One-shot status for both workspace live stacks.
# Usage: scripts/live_mode_status_all.sh

DB_PATH="./.local/state/slack_mirror_test.db"

UNITS=(
  slack-mirror-webhooks-default.service
  slack-mirror-events-default.service
  slack-mirror-embeddings-default.service
  slack-mirror-webhooks-soylei.service
  slack-mirror-events-soylei.service
  slack-mirror-embeddings-soylei.service
)

echo "== systemd user services =="
systemctl --user --no-pager --full status "${UNITS[@]}" 2>/dev/null | sed -n '1,220p' || true

echo
if [[ -f "${DB_PATH}" ]]; then
  echo "== latest mirrored messages by workspace =="
  sqlite3 "${DB_PATH}" "select w.name, datetime(max(CAST(m.ts as real)), 'unixepoch', 'localtime') from messages m join workspaces w on w.id=m.workspace_id group by w.name order by w.name;" || true

  echo
  echo "== events by workspace/status =="
  sqlite3 "${DB_PATH}" "select w.name, e.status, count(*) from events e join workspaces w on w.id=e.workspace_id group by w.name,e.status order by w.name,e.status;" || true

  echo
  echo "== embedding_jobs by workspace/status =="
  sqlite3 "${DB_PATH}" "select w.name, j.status, count(*) from embedding_jobs j join workspaces w on w.id=j.workspace_id group by w.name,j.status order by w.name,j.status;" || true
else
  echo "DB not found: ${DB_PATH}"
fi
