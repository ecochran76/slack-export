#!/usr/bin/env bash
set -euo pipefail

# Install systemd --user units for always-on slack-mirror live mode.
#
# Usage:
#   scripts/install_live_mode_systemd_user.sh [workspace] [config] [legacy_port_ignored]
# Example:
#   scripts/install_live_mode_systemd_user.sh default config.local.yaml
#
# Socket Mode is used for inbound Slack events, so no local port forwarding/tunnel is required.

WORKSPACE="${1:-default}"
CONFIG="${2:-config.local.yaml}"
LEGACY_PORT="${3:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
SLACK_MIRROR_BIN="${REPO_ROOT}/.venv/bin/slack-mirror"
if [[ ! -x "${SLACK_MIRROR_BIN}" ]]; then
  SLACK_MIRROR_BIN="$(command -v slack-mirror || true)"
fi
if [[ -z "${SLACK_MIRROR_BIN}" ]]; then
  echo "slack-mirror not found in PATH or .venv/bin" >&2
  exit 1
fi

if [[ -n "${LEGACY_PORT}" ]]; then
  echo "Note: port argument '${LEGACY_PORT}' is ignored in Socket Mode." >&2
fi

mkdir -p "${UNIT_DIR}"

RECEIVER_UNIT="slack-mirror-webhooks-${WORKSPACE}.service"
EVENTS_UNIT="slack-mirror-events-${WORKSPACE}.service"
EMBEDDINGS_UNIT="slack-mirror-embeddings-${WORKSPACE}.service"

cat > "${UNIT_DIR}/${RECEIVER_UNIT}" <<EOF
[Unit]
Description=Slack Mirror Socket Mode receiver (${WORKSPACE})
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${REPO_ROOT}
ExecStart=${SLACK_MIRROR_BIN} --config ${CONFIG} mirror serve-socket-mode --workspace ${WORKSPACE}
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

cat > "${UNIT_DIR}/${EVENTS_UNIT}" <<EOF
[Unit]
Description=Slack Mirror event processor (${WORKSPACE})
After=network-online.target ${RECEIVER_UNIT}
Wants=network-online.target ${RECEIVER_UNIT}

[Service]
Type=simple
WorkingDirectory=${REPO_ROOT}
ExecStart=${SLACK_MIRROR_BIN} --config ${CONFIG} mirror process-events --workspace ${WORKSPACE} --loop --interval 2
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

cat > "${UNIT_DIR}/${EMBEDDINGS_UNIT}" <<EOF
[Unit]
Description=Slack Mirror embedding jobs processor (${WORKSPACE})
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
systemctl --user enable "${RECEIVER_UNIT}" "${EVENTS_UNIT}" "${EMBEDDINGS_UNIT}" >/dev/null
systemctl --user restart "${RECEIVER_UNIT}" "${EVENTS_UNIT}" "${EMBEDDINGS_UNIT}"

echo "Installed + started user services:"
echo "  - ${RECEIVER_UNIT}"
echo "  - ${EVENTS_UNIT}"
echo "  - ${EMBEDDINGS_UNIT}"
echo
systemctl --user --no-pager --full status \
  "${RECEIVER_UNIT}" \
  "${EVENTS_UNIT}" \
  "${EMBEDDINGS_UNIT}" | sed -n '1,120p'

echo
echo "Useful commands:"
echo "  systemctl --user restart ${RECEIVER_UNIT} ${EVENTS_UNIT} ${EMBEDDINGS_UNIT}"
echo "  systemctl --user stop ${RECEIVER_UNIT} ${EVENTS_UNIT} ${EMBEDDINGS_UNIT}"
echo "  journalctl --user -u ${RECEIVER_UNIT} -u ${EVENTS_UNIT} -u ${EMBEDDINGS_UNIT} -f"
