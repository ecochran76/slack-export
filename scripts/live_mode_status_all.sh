#!/usr/bin/env bash
set -euo pipefail

# One-shot status for both workspace live stacks.
# Usage: scripts/live_mode_status_all.sh [default_port] [soylei_port]

DEFAULT_PORT="${1:-8787}"
SOYLEI_PORT="${2:-8788}"
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
systemctl --user --no-pager --full status "${UNITS[@]}" 2>/dev/null | sed -n '1,180p' || true

echo
echo "== webhook health =="
echo -n "default (:${DEFAULT_PORT}): "
curl --max-time 2 -fsS "http://127.0.0.1:${DEFAULT_PORT}/healthz" && echo || echo "DOWN"
echo -n "soylei  (:${SOYLEI_PORT}): "
curl --max-time 2 -fsS "http://127.0.0.1:${SOYLEI_PORT}/healthz" && echo || echo "DOWN"

echo
if [[ -f "${DB_PATH}" ]]; then
  echo "== events by workspace/status =="
  sqlite3 "${DB_PATH}" "select w.name, e.status, count(*) from events e join workspaces w on w.id=e.workspace_id group by w.name,e.status order by w.name,e.status;" || true

  echo
  echo "== embedding_jobs by workspace/status =="
  sqlite3 "${DB_PATH}" "select w.name, j.status, count(*) from embedding_jobs j join workspaces w on w.id=j.workspace_id group by w.name,j.status order by w.name,j.status;" || true
else
  echo "DB not found: ${DB_PATH}"
fi
