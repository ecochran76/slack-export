#!/usr/bin/env bash
set -euo pipefail

# Install systemd --user units for always-on slack-mirror live mode.
#
# Usage:
#   scripts/install_live_mode_systemd_user.sh [workspace] [config] [port]
# Example:
#   scripts/install_live_mode_systemd_user.sh default config.local.yaml 8787

WORKSPACE="${1:-default}"
CONFIG="${2:-config.local.yaml}"
PORT="${3:-8787}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
SLACK_MIRROR_BIN="$(command -v slack-mirror || true)"
if [[ -z "${SLACK_MIRROR_BIN}" ]]; then
  echo "slack-mirror not found in PATH" >&2
  exit 1
fi

mkdir -p "${UNIT_DIR}"

cat > "${UNIT_DIR}/slack-mirror-webhooks.service" <<EOF
[Unit]
Description=Slack Mirror webhook receiver
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${REPO_ROOT}
ExecStart=${SLACK_MIRROR_BIN} --config ${CONFIG} mirror serve-webhooks --workspace ${WORKSPACE} --bind 127.0.0.1 --port ${PORT}
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

cat > "${UNIT_DIR}/slack-mirror-events.service" <<EOF
[Unit]
Description=Slack Mirror event processor loop
After=network-online.target slack-mirror-webhooks.service
Wants=network-online.target slack-mirror-webhooks.service

[Service]
Type=simple
WorkingDirectory=${REPO_ROOT}
ExecStart=${SLACK_MIRROR_BIN} --config ${CONFIG} mirror process-events --workspace ${WORKSPACE} --loop --interval 2
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

cat > "${UNIT_DIR}/slack-mirror-embeddings.service" <<EOF
[Unit]
Description=Slack Mirror embedding jobs processor loop
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${REPO_ROOT}
ExecStart=/usr/bin/env bash -lc 'while true; do "${SLACK_MIRROR_BIN}" --config ${CONFIG} mirror process-embedding-jobs --workspace ${WORKSPACE} --limit 500; sleep 5; done'
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now slack-mirror-webhooks.service slack-mirror-events.service slack-mirror-embeddings.service

echo "Installed + started user services:"
echo "  - slack-mirror-webhooks.service"
echo "  - slack-mirror-events.service"
echo "  - slack-mirror-embeddings.service"
echo
systemctl --user --no-pager --full status \
  slack-mirror-webhooks.service \
  slack-mirror-events.service \
  slack-mirror-embeddings.service | sed -n '1,80p'

echo
echo "Useful commands:"
echo "  systemctl --user restart slack-mirror-webhooks.service slack-mirror-events.service slack-mirror-embeddings.service"
echo "  systemctl --user stop slack-mirror-webhooks.service slack-mirror-events.service slack-mirror-embeddings.service"
echo "  journalctl --user -u slack-mirror-webhooks.service -u slack-mirror-events.service -u slack-mirror-embeddings.service -f"
