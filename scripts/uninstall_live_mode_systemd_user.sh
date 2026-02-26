#!/usr/bin/env bash
set -euo pipefail

# Uninstall systemd --user units for slack-mirror live mode.
#
# Usage:
#   scripts/uninstall_live_mode_systemd_user.sh

UNIT_DIR="${HOME}/.config/systemd/user"
UNITS=(
  "slack-mirror-webhooks.service"
  "slack-mirror-events.service"
  "slack-mirror-embeddings.service"
)

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
