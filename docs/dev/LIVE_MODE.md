# Live Mode Operations

This runbook keeps Slack mirror ingest + search freshness running continuously.

## What "live" means here

Three long-running workers:

1. **Webhook receiver**
   - `mirror serve-webhooks`
   - Accepts Slack Events API traffic and stores pending events.
2. **Event processor**
   - `mirror process-events --loop`
   - Applies new/edit/delete/channel membership events to DB.
3. **Embedding processor loop**
   - `mirror process-embedding-jobs` in a short sleep loop
   - Keeps semantic search near-real-time.

## Quick start (tmux)

From repo root:

```bash
scripts/live_mode_tmux.sh default config.local.yaml
```

Then attach:

```bash
tmux attach -t slack-mirror-live-default
```

Stop:

```bash
tmux kill-session -t slack-mirror-live-default
```

## Manual commands

Run each command in its own terminal/tab:

```bash
slack-mirror --config config.local.yaml mirror serve-webhooks --workspace default --bind 127.0.0.1 --port 8787
```

```bash
slack-mirror --config config.local.yaml mirror process-events --workspace default --loop --interval 2
```

```bash
while true; do
  slack-mirror --config config.local.yaml mirror process-embedding-jobs --workspace default --limit 500
  sleep 5
done
```

## Health checks

Use these spot checks while live mode is running:

```bash
curl -fsS http://127.0.0.1:8787/healthz
```

```bash
sqlite3 cache/slack_mirror.db "select status, count(*) from events group by status order by status;"
```

```bash
sqlite3 cache/slack_mirror.db "select status, count(*) from embedding_jobs group by status order by status;"
```

## Auto-start via systemd (user services)

Install and start all three services:

```bash
scripts/install_live_mode_systemd_user.sh default config.local.yaml 8787
```

Check status:

```bash
systemctl --user status slack-mirror-webhooks.service slack-mirror-events.service slack-mirror-embeddings.service
```

Follow logs:

```bash
journalctl --user -u slack-mirror-webhooks.service -u slack-mirror-events.service -u slack-mirror-embeddings.service -f
```

Enable auto-start after reboot/login:

```bash
systemctl --user enable slack-mirror-webhooks.service slack-mirror-events.service slack-mirror-embeddings.service
```

Uninstall (disable/stop/remove units):

```bash
scripts/uninstall_live_mode_systemd_user.sh
```

(Optional) keep user services running without active login session:

```bash
loginctl enable-linger "$USER"
```

## Notes

- Keep event processor interval low (1-3s) for responsive updates.
- Embedding loop frequency trades off freshness vs compute; 5-15s is a good default.
- For local dev, tmux is easiest to inspect interactively; systemd is better for unattended operation.
