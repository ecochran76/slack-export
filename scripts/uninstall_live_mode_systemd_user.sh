#!/usr/bin/env bash
set -euo pipefail

# Uninstall systemd --user units for slack-mirror live mode.
#
# Usage:
#   scripts/uninstall_live_mode_systemd_user.sh [workspace]

UNIT_DIR="${HOME}/.config/systemd/user"
WORKSPACE="${1:-}"
if [[ -n "${WORKSPACE}" ]]; then
  UNITS=(
    "slack-mirror-webhooks-${WORKSPACE}.service"
    "slack-mirror-daemon-${WORKSPACE}.service"
    "slack-mirror-events-${WORKSPACE}.service"
    "slack-mirror-embeddings-${WORKSPACE}.service"
  )
else
  UNITS=(
    "slack-mirror-webhooks.service"
    "slack-mirror-events.service"
    "slack-mirror-embeddings.service"
    "slack-mirror-webhooks-default.service"
    "slack-mirror-daemon-default.service"
    "slack-mirror-events-default.service"
    "slack-mirror-embeddings-default.service"
    "slack-mirror-webhooks-soylei.service"
    "slack-mirror-daemon-soylei.service"
    "slack-mirror-events-soylei.service"
    "slack-mirror-embeddings-soylei.service"
  )
fi

echo "Stopping + disabling services (if present)..."
for u in "${UNITS[@]}"; do
  systemctl --user disable --now "$u" 2>/dev/null || true
done

echo "Removing unit files..."
for u in "${UNITS[@]}"; do
  rm -f "${UNIT_DIR}/${u}"
done

systemctl --user daemon-reload
systemctl --user reset-failed

echo "Uninstall complete."
echo
systemctl --user --no-pager --full status "${UNITS[@]}" 2>/dev/null || true
