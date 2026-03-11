# Live Mode Operations

This runbook keeps Slack mirror ingest + search freshness running continuously.

## Recommended config target

For long-lived user installs, prefer the user-scope config/state:

- Config: `~/.config/slack-mirror/config.yaml`
- DB: `~/.local/state/slack-mirror/slack_mirror.db`
- Cache: `~/.local/cache/slack-mirror`

Repo-local `config.local.yaml` is still useful for dev/test, but it should not be your default unattended runtime.

## What "live" means here

Three long-running workers:

1. **Socket Mode receiver**
   - `mirror serve-socket-mode`
   - Receives Slack events and stores pending events in the configured DB.
2. **Event processor**
   - `mirror process-events --loop`
   - Applies new/edit/delete/channel membership events to DB.
3. **Embedding processor loop**
   - `mirror process-embedding-jobs` in a short sleep loop
   - Keeps semantic search near-real-time.

## Quick start (tmux)

From repo root:

```bash
scripts/live_mode_tmux.sh default
```

If `~/.config/slack-mirror/config.yaml` exists, the helper will prefer it automatically. Otherwise it falls back to `config.local.yaml`.

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
slack-mirror --config ~/.config/slack-mirror/config.yaml mirror serve-socket-mode --workspace default
```

```bash
slack-mirror --config ~/.config/slack-mirror/config.yaml mirror process-events --workspace default --loop --interval 2
```

```bash
while true; do
  slack-mirror --config ~/.config/slack-mirror/config.yaml mirror process-embedding-jobs --workspace default --limit 500
  sleep 5
done
```

## Health checks

Use these spot checks while live mode is running:

```bash
systemctl --user list-units 'slack-mirror*' --all --no-pager
```

```bash
sqlite3 ~/.local/state/slack-mirror/slack_mirror.db "select status, count(*) from events group by status order by status;"
```

```bash
sqlite3 ~/.local/state/slack-mirror/slack_mirror.db "select status, count(*) from embedding_jobs group by status order by status;"
```

## Auto-start via systemd (user services)

Install and start all three services:

```bash
scripts/install_live_mode_systemd_user.sh default
scripts/install_live_mode_systemd_user.sh soylei
```

If `~/.config/slack-mirror/config.yaml` exists, the installer will prefer it automatically. You can still override the config path explicitly:

```bash
scripts/install_live_mode_systemd_user.sh default "$HOME/.config/slack-mirror/config.yaml"
```

Check status:

```bash
systemctl --user status slack-mirror-webhooks-default.service slack-mirror-events-default.service slack-mirror-embeddings-default.service
```

Follow logs:

```bash
journalctl --user -u slack-mirror-webhooks-default.service -u slack-mirror-events-default.service -u slack-mirror-embeddings-default.service -f
```

Enable auto-start after reboot/login:

```bash
systemctl --user enable slack-mirror-webhooks-default.service slack-mirror-events-default.service slack-mirror-embeddings-default.service
```

(Optional) keep user services running without active login session:

```bash
loginctl enable-linger "$USER"
```

## Notes

- Keep event processor interval low (1-3s) for responsive updates.
- Embedding loop frequency trades off freshness vs compute; 5-15s is a good default.
- For local dev, tmux is easiest to inspect interactively; systemd is better for unattended operation.
- If the mirror DB ever seems stale, first confirm the live services are pointed at the same config/DB you expect.
