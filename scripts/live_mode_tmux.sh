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

BASE="slack-mirror --config ${CONFIG}"

tmux new-session -d -s "${SESSION}" -n webhooks

tmux send-keys -t "${SESSION}:webhooks" "cd $(pwd) && ${BASE} mirror serve-webhooks --workspace ${WORKSPACE} --bind 127.0.0.1 --port 8787" C-m

tmux split-window -h -t "${SESSION}:webhooks"
tmux send-keys -t "${SESSION}:webhooks.1" "cd $(pwd) && ${BASE} mirror process-events --workspace ${WORKSPACE} --loop --interval 2" C-m

tmux split-window -v -t "${SESSION}:webhooks.1"
tmux send-keys -t "${SESSION}:webhooks.2" "cd $(pwd) && while true; do ${BASE} mirror process-embedding-jobs --workspace ${WORKSPACE} --limit 500; sleep 5; done" C-m

tmux select-layout -t "${SESSION}:webhooks" tiled

echo "Started tmux session: ${SESSION}"
echo "Attach: tmux attach -t ${SESSION}"
echo "Stop: tmux kill-session -t ${SESSION}"
