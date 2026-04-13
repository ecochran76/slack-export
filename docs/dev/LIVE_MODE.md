# Live Mode Operations

This runbook keeps Slack mirror ingest + search freshness running continuously.

## Recommended config target

For long-lived user installs, prefer the user-scope config/state:

- Config: `~/.config/slack-mirror/config.yaml`
- DB: `~/.local/state/slack-mirror/slack_mirror.db`
- Cache: `~/.local/cache/slack-mirror`

Repo-local `config.local.yaml` is still useful for dev/test, but it should not be your default unattended runtime.

## What "live" means here

Two long-running services per workspace:

1. **Socket Mode receiver**
   - `mirror serve-socket-mode`
   - Receives Slack events and stores pending events in the configured DB.
2. **Unified daemon**
   - `mirror daemon`
   - Processes pending events, processes embedding jobs, and runs periodic reconcile.

Do not run the older split `process-events --loop` and `process-embedding-jobs` services alongside the unified daemon for the same workspace. That creates duplicate writers and can produce `sqlite3.OperationalError: database is locked`.

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
slack-mirror --config ~/.config/slack-mirror/config.yaml mirror daemon --workspace default --interval 2 --event-limit 1000 --embedding-limit 500 --model local-hash-128 --reconcile-minutes 2 --reconcile-channel-limit 1000 --auth-mode user
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

Install and start the supported two-service topology:

```bash
scripts/install_live_mode_systemd_user.sh default
scripts/install_live_mode_systemd_user.sh soylei
```

If `~/.config/slack-mirror/config.yaml` exists, the installer will prefer it automatically. You can still override the config path explicitly:

```bash
scripts/install_live_mode_systemd_user.sh default "$HOME/.config/slack-mirror/config.yaml"
```

The user-scope installer and updater validate the managed config, DB, workspace sync, and API service automatically, but they do not install these live workspace units for you. Treat `slack-mirror user-env validate-live` as the full gate only after the workspace live units are installed.

Check status:

```bash
systemctl --user status slack-mirror-webhooks-default.service slack-mirror-daemon-default.service
```

Validate the supported managed contract:

```bash
slack-mirror user-env validate-live
```

Machine-readable validation for shell automation:

```bash
slack-mirror user-env validate-live --json
```

One-command operator smoke gate:

```bash
slack-mirror user-env check-live
```

Machine-readable smoke gate:

```bash
slack-mirror user-env check-live --json
```

Bounded recovery planner:

```bash
slack-mirror user-env recover-live
```

Apply the safe remediations:

```bash
slack-mirror user-env recover-live --apply
```

Follow logs:

```bash
journalctl --user -u slack-mirror-webhooks-default.service -u slack-mirror-daemon-default.service -f
```

Enable auto-start after reboot/login:

```bash
systemctl --user enable slack-mirror-webhooks-default.service slack-mirror-daemon-default.service
```

(Optional) keep user services running without active login session:

```bash
loginctl enable-linger "$USER"
```

## Notes

- Keep daemon interval low (1-3s) for responsive updates.
- The daemon owns embedding job draining and periodic reconcile.
- For local dev, tmux is easiest to inspect interactively; systemd is better for unattended operation.
- If the mirror DB ever seems stale, first confirm the live services are pointed at the same config/DB you expect.
- Use `scripts/live_mode_status.sh <workspace>` or `scripts/live_mode_status_all.sh` to spot duplicate topology, queue backlog, and recent freshness.

## Failure Classes And Recovery

`slack-mirror user-env validate-live` now emits stable issue classes so the first recovery step is obvious.

Common hard failures:

- `CONFIG_MISSING` or `CONFIG_INVALID`
  - restore or fix `~/.config/slack-mirror/config.yaml`, then rerun validation
- `DB_MISSING`, `DB_UNREADABLE`, or `WORKSPACE_DB_MISSING`
  - run `slack-mirror-user mirror init`
  - run `slack-mirror-user workspaces sync-config`
  - confirm the configured DB path is the one the live services use
- `OUTBOUND_TOKEN_MISSING` or `OUTBOUND_USER_TOKEN_MISSING`
  - set explicit write-capable outbound tokens in config for the affected workspace
- `API_UNIT_MISSING`, `API_UNIT_INACTIVE`, `LIVE_UNIT_MISSING`, or `LIVE_UNIT_INACTIVE`
  - run `slack-mirror user-env update` if the managed API unit is missing
  - run `scripts/install_live_mode_systemd_user.sh <workspace>` if the workspace live units are missing
  - restart the affected units with `systemctl --user restart ...`
  - inspect logs with `journalctl --user -u <unit> -n 50`
- `DUPLICATE_TOPOLOGY`
  - disable the split legacy workers:
    `systemctl --user disable --now slack-mirror-events-<workspace>.service slack-mirror-embeddings-<workspace>.service`
- `DAEMON_HEARTBEAT_MISSING` or `DAEMON_HEARTBEAT_STALE`
  - the daemon unit may be active but not making progress
  - restart it with `systemctl --user restart slack-mirror-daemon-<workspace>.service`
  - inspect logs with `journalctl --user -u slack-mirror-daemon-<workspace>.service -n 50`
  - confirm heartbeat files under the managed DB directory are advancing
- `STALE_MIRROR`
  - inspect freshness classification with:
    `slack-mirror --config ~/.config/slack-mirror/config.yaml mirror status --workspace <workspace> --healthy --enforce-stale --classify-access`
  - treat this as an observability warning first; quiet historical channels are common in large workspaces
  - the access report now includes:
    - percentages for A/B/C buckets
    - a simple interpretation label
    - sample inactive and zero-message channels
    - channel class and last-message age on inactive samples
    - a split between shell-like empty IM/MPIM channels and unexpected empty public/private channels
    - explicit zero-message statuses:
      - `shell_channel_no_messages`
      - `unexpected_empty_channel`
  - full `validate-live` now suppresses `STALE_MIRROR` when:
    - the workspace has active recent channels, and
    - the zero-message bucket has no unexpected empty public/private channels
  - in plain-text output, suppressed stale evidence is still surfaced as an `OK` line with the stale count and suppression rationale
  - if it coincides with daemon-heartbeat or queue failures, then it is strong evidence of a real mirror-health problem

Warnings:

- `EVENT_ERRORS`
- `EMBEDDING_ERRORS`
- `EVENT_PENDING`
- `EMBEDDING_PENDING`
- `STALE_MIRROR`
- `RECONCILE_REPAIR_WARNINGS`
- `RECONCILE_REPAIR_FAILURES`

Live-mode hard failures also include:

- `EVENT_BACKLOG`
- `EMBEDDING_BACKLOG`

In full live validation, queue error rows fail immediately, and sustained pending backlog beyond the built-in thresholds also fails:

- pending events over `100`
- pending embedding jobs over `1000`
- daemon heartbeat older than `10m`

Stale-channel counts remain warnings. They are useful for spotting coverage gaps, but they are not by themselves proof that a live mirror is failing.
Warnings do not fail validation, but they mean the topology is healthy while some queued work still needs operator attention.

`validate-live` now also surfaces the last persisted `mirror reconcile-files` result per workspace when one exists. That gives operators a compact summary of the most recent repair batch without rerunning reconciliation. If the last repair batch recorded warnings or failures, validation emits:

- `RECONCILE_REPAIR_WARNINGS`
- `RECONCILE_REPAIR_FAILURES`

These stay in the warning class. They are intended to expose file-repair regressions, not to redefine the core live-service health gate.

`slack-mirror user-env recover-live` intentionally auto-remediates only the safe restart class:

- daemon-reload for `systemd --user`
- restart inactive managed API service
- restart inactive managed workspace live units

It does not auto-fix config, token, DB, workspace-sync, duplicate-topology, or queue-content problems.

For shell automation, prefer:

- `slack-mirror user-env status --json`
- `slack-mirror user-env validate-live --json`
- `slack-mirror user-env check-live --json`
- `slack-mirror user-env recover-live --json`
