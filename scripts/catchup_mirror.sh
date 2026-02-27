#!/usr/bin/env bash
set -euo pipefail

# Catch-up sweep for known workspaces + optional completeness report.
# Designed for cron/systemd timer usage.

CFG="${1:-config.local.yaml}"

run_ws() {
  local ws="$1"
  echo "== catch-up workspace=${ws} =="
  slack-mirror --config "$CFG" mirror backfill --workspace "$ws" --auth-mode user --include-messages || true
  slack-mirror --config "$CFG" mirror process-embedding-jobs --workspace "$ws" --limit 5000 || true
}

run_ws default
run_ws soylei

python scripts/audit_mirror_completeness.py --db ./.local/state/slack_mirror_test.db --tz America/Chicago --stale-hours 24
