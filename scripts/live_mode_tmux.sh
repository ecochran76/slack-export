#!/usr/bin/env bash
set -euo pipefail

# Start always-on local live mirror workers in tmux.
#
# Usage:
#   scripts/live_mode_tmux.sh [workspace] [config]
# Example:
#   scripts/live_mode_tmux.sh default config.local.yaml

WORKSPACE="${1:-default}"
CONFIG="${2:-config.local.yaml}"
SESSION="slack-mirror-live-${WORKSPACE}"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found. Install tmux first." >&2
  exit 1
fi

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "tmux session already exists: ${SESSION}"
  echo "Attach with: tmux attach -t ${SESSION}"
  exit 0
fi

BIN="$(pwd)/.venv/bin/slack-mirror"
if [[ ! -x "${BIN}" ]]; then
  BIN="slack-mirror"
fi
BASE="${BIN} --config ${CONFIG}"

tmux new-session -d -s "${SESSION}" -n socket-mode

tmux send-keys -t "${SESSION}:socket-mode" "cd $(pwd) && ${BASE} mirror serve-socket-mode --workspace ${WORKSPACE}" C-m

tmux split-window -h -t "${SESSION}:socket-mode"
tmux send-keys -t "${SESSION}:socket-mode.1" "cd $(pwd) && ${BASE} mirror process-events --workspace ${WORKSPACE} --loop --interval 2" C-m

tmux split-window -v -t "${SESSION}:socket-mode.1"
tmux send-keys -t "${SESSION}:socket-mode.2" "cd $(pwd) && while true; do ${BASE} mirror process-embedding-jobs --workspace ${WORKSPACE} --limit 500; sleep 5; done" C-m

tmux select-layout -t "${SESSION}:socket-mode" tiled

echo "Started tmux session: ${SESSION}"
echo "Attach: tmux attach -t ${SESSION}"
echo "Stop: tmux kill-session -t ${SESSION}"
