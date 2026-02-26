---
name: slack-mirror-live-ops
description: Operate Slack Mirror in always-on mode (systemd/tmux), including single or multi-workspace service layout, webhook health, queue health, and indexing freshness verification. Use for requests like "start live sync", "both workspaces active?", "status", "set up dual workspace services".
---

# Slack Mirror Live Ops

## Primary outcomes

- Keep webhook/event/embedding workers running continuously.
- Verify no queue backlog and search freshness stays current.

## Standard commands

- Single workspace service install:
  - `scripts/install_live_mode_systemd_user.sh <workspace> <config> <port>`
- Dual workspace status:
  - `scripts/live_mode_status_all.sh 8787 8788`
- Service status:
  - `systemctl --user status <unit...>`
- Logs:
  - `journalctl --user -u <unit...> -f`

## Dual workspace model

Use suffixed services per workspace (avoid clobbering unsuffixed units):

- `slack-mirror-webhooks-default.service`
- `slack-mirror-events-default.service`
- `slack-mirror-embeddings-default.service`
- `slack-mirror-webhooks-soylei.service`
- `slack-mirror-events-soylei.service`
- `slack-mirror-embeddings-soylei.service`

## Fast triage

1. If webhooks fail with signing secret error, fix workspace `signing_secret` env mapping.
2. If service flaps, check absolute binary path and restart policy.
3. If indexing lags, check `embedding_jobs` backlog and worker loop.
4. If both services show healthy but no new data, verify event timestamps in DB.
