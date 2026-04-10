#!/usr/bin/env bash
set -euo pipefail

# Install systemd --user units for always-on slack-mirror live mode.
#
# Usage:
#   scripts/install_live_mode_systemd_user.sh [workspace] [config] [legacy_port_ignored]
# Examples:
#   scripts/install_live_mode_systemd_user.sh default
#   scripts/install_live_mode_systemd_user.sh default "$HOME/.config/slack-mirror/config.yaml"
#
# Socket Mode is used for inbound Slack events, so no local port forwarding/tunnel is required.
# Supported steady-state topology per workspace:
#   - one Socket Mode receiver
#   - one unified daemon
# Do not run the older split events/embeddings units alongside the daemon.

WORKSPACE="${1:-default}"
USER_CONFIG_DEFAULT="${HOME}/.config/slack-mirror/config.yaml"
if [[ -n "${2:-}" ]]; then
  CONFIG="${2}"
elif [[ -f "${USER_CONFIG_DEFAULT}" ]]; then
  CONFIG="${USER_CONFIG_DEFAULT}"
else
  CONFIG="config.local.yaml"
fi
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
DAEMON_UNIT="slack-mirror-daemon-${WORKSPACE}.service"
LEGACY_EVENTS_UNIT="slack-mirror-events-${WORKSPACE}.service"
LEGACY_EMBEDDINGS_UNIT="slack-mirror-embeddings-${WORKSPACE}.service"

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

cat > "${UNIT_DIR}/${DAEMON_UNIT}" <<EOF
[Unit]
Description=Slack Mirror unified daemon (${WORKSPACE})
After=network-online.target ${RECEIVER_UNIT}
Wants=network-online.target ${RECEIVER_UNIT}

[Service]
Type=simple
WorkingDirectory=${REPO_ROOT}
ExecStart=${SLACK_MIRROR_BIN} --config ${CONFIG} mirror daemon --workspace ${WORKSPACE} --interval 2 --event-limit 1000 --embedding-limit 500 --model local-hash-128 --reconcile-minutes 2 --reconcile-channel-limit 1000 --auth-mode user
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user disable --now "${LEGACY_EVENTS_UNIT}" "${LEGACY_EMBEDDINGS_UNIT}" >/dev/null 2>&1 || true
systemctl --user enable "${RECEIVER_UNIT}" "${DAEMON_UNIT}" >/dev/null
systemctl --user restart "${RECEIVER_UNIT}" "${DAEMON_UNIT}"

echo "Installed + started user services:"
echo "  - ${RECEIVER_UNIT}"
echo "  - ${DAEMON_UNIT}"
echo "  - config: ${CONFIG}"
echo "Disabled legacy units if present:"
echo "  - ${LEGACY_EVENTS_UNIT}"
echo "  - ${LEGACY_EMBEDDINGS_UNIT}"
echo
systemctl --user --no-pager --full status \
  "${RECEIVER_UNIT}" \
  "${DAEMON_UNIT}" | sed -n '1,120p'

echo
echo "Useful commands:"
echo "  systemctl --user restart ${RECEIVER_UNIT} ${DAEMON_UNIT}"
echo "  systemctl --user stop ${RECEIVER_UNIT} ${DAEMON_UNIT}"
echo "  journalctl --user -u ${RECEIVER_UNIT} -u ${DAEMON_UNIT} -f"
