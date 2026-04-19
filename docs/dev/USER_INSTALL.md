# User-Scope Install / Update / Uninstall

This installs `slack-mirror` into an isolated user-owned runtime that is independent of your git checkout.

## What it sets up

- App snapshot: `~/.local/share/slack-mirror/app`
- Previous app snapshot for rollback: `~/.local/share/slack-mirror/app.previous`
- Virtualenv: `~/.local/share/slack-mirror/venv`
- Runtime state: `~/.local/state/slack-mirror`
  - DB: `~/.local/state/slack-mirror/slack_mirror.db`
- Runtime cache: `~/.local/cache/slack-mirror`
- Config: `~/.config/slack-mirror/config.yaml`
- Wrapper CLI: `~/.local/bin/slack-mirror-user`
- API launcher: `~/.local/bin/slack-mirror-api`
- MCP launcher: `~/.local/bin/slack-mirror-mcp`
- API service: `~/.config/systemd/user/slack-mirror-api.service`
- Runtime report service: `~/.config/systemd/user/slack-mirror-runtime-report.service`
- Runtime report timer: `~/.config/systemd/user/slack-mirror-runtime-report.timer`

The wrapper injects env vars for DB/cache and always points to the user config path.
The API launcher runs `slack-mirror api serve` with the managed config.
The MCP launcher runs `slack-mirror mcp serve` with the managed config.
The API service runs the API launcher under `systemd --user`.
The runtime report timer runs `slack-mirror-user user-env snapshot-report --name scheduled-runtime-report` hourly under `systemd --user`.
The managed install and update path now validates that the MCP launcher can answer a real MCP health request, not just that the launcher file exists.
`user-env status` and `user-env check-live` also run a bounded concurrent MCP readiness probe so multi-client stdio usage can be verified before you add several agent clients.

## Fresh Install To First Workspace

This is the canonical operator path for a new local install.

Use it when you want to go from a fresh machine or fresh user account to:

- one working managed install
- one configured Slack workspace
- live per-workspace services installed
- one bootstrapped browser user
- one successful browser smoke on `http://slack.localhost`

### Per-install vs per-workspace

Per-install steps:

- from a repo checkout, `uv run slack-mirror user-env install`
- edit `~/.config/slack-mirror/config.yaml`
- `slack-mirror-user user-env provision-frontend-user ...`

Per-workspace steps:

- add a workspace entry under `workspaces:`
- create a private Slack app for that workspace from the manifest in `manifests/`
- install that workspace's Slack credentials into the configured dotenv file with `tenants credentials`
- `slack-mirror-user workspaces sync-config`
- `slack-mirror-user workspaces verify --require-explicit-outbound`
- `scripts/install_live_mode_systemd_user.sh <workspace>`

### Recommended first-run sequence

1. Install the managed user runtime:

```bash
uv run slack-mirror user-env install
```

If `slack-mirror` is already installed on your shell `PATH`, `slack-mirror user-env install` is equivalent. From a fresh repo checkout, prefer the `uv run ...` form so the installer uses the repo dependency set.
The installer now also creates the configured dotenv file on first run if it does not exist yet, so the managed config can load before you have copied any Slack credentials.

2. Edit `~/.config/slack-mirror/config.yaml` and define at least:

- `service.auth.enabled: true`
- `exports.local_base_url: http://slack.localhost`
- one enabled workspace under `workspaces:`
- explicit read and write credentials for that workspace

For field-level config guidance, see [docs/CONFIG.md](/home/ecochran76/workspace.local/slack-export/docs/CONFIG.md).
For Slack app creation, credential collection, and the app-manifest location, see [docs/SLACK_MANIFEST.md](/home/ecochran76/workspace.local/slack-export/docs/SLACK_MANIFEST.md).

3. Sync the configured workspaces into the managed DB:

```bash
slack-mirror-user workspaces sync-config
```

4. Verify the workspace config with explicit outbound-write requirements:

```bash
slack-mirror-user workspaces verify --require-explicit-outbound
```

5. Install the live per-workspace services for the workspace you just added:

```bash
scripts/install_live_mode_systemd_user.sh default
```

Repeat that command for each additional workspace name.

6. Run the one-command managed smoke gate:

```bash
slack-mirror-user user-env check-live
slack-mirror-user user-env check-live --json
```

Use `check-live` as the best single signoff that the managed install, config, API service, MCP launcher, workspace sync, and live units are aligned.

7. Bootstrap the first browser user without reopening public self-registration:

```bash
export SLACK_MIRROR_BOOTSTRAP_PASSWORD='choose-a-long-random-password'
slack-mirror-user user-env provision-frontend-user \
  --username you@example.com \
  --password-env SLACK_MIRROR_BOOTSTRAP_PASSWORD
```

8. Smoke the browser surface:

- open `http://slack.localhost/login`
- sign in with the provisioned user
- verify `/`, `/settings`, `/runtime/reports`, and `/exports`

9. Capture a shareable machine-readable runtime signoff when needed:

```bash
slack-mirror-user user-env snapshot-report --name first-install
slack-mirror-user user-env snapshot-report --name first-install --json
```

### Adding another workspace later

When the install already exists and you are onboarding an additional workspace:

1. Create the disabled tenant scaffold and rendered JSON Slack app manifest:

```bash
slack-mirror-user tenants onboard \
  --name polymer \
  --domain polymerconsul-clo9441 \
  --display-name "Polymer Consulting Group"
```

2. Create the Slack app at `https://api.slack.com/apps` from the rendered JSON manifest printed by the command.
3. Collect the team ID, bot token, app token, signing secret, and optional user token.
4. Install those values into the configured dotenv file without editing YAML or echoing secrets in status output:

```bash
slack-mirror-user tenants credentials polymer \
  --credential team_id=T... \
  --credential token=xoxb-... \
  --credential outbound_token=xoxb-... \
  --credential app_token=xapp-... \
  --credential signing_secret=...
```

Optional user-token fields are `user_token=xoxp-...` and `outbound_user_token=xoxp-...`.
The command writes the deterministic `SLACK_<WORKSPACE>_*` variables into the dotenv path configured by `~/.config/slack-mirror/config.yaml`, creates a timestamped backup when the file already exists, and reports only installed variable names plus redacted readiness.

5. Review redacted readiness:

```bash
slack-mirror-user tenants status polymer
```

6. When credentials are present, activate the tenant:

```bash
slack-mirror-user tenants activate polymer
```

This enables the workspace, syncs it into the DB, and installs or refreshes the per-workspace live units.

7. Run `slack-mirror-user workspaces verify --workspace <workspace> --require-explicit-outbound`.
8. Rerun `slack-mirror-user user-env check-live`.

If you need to enable and sync config without starting systemd units, use:

```bash
slack-mirror-user tenants activate polymer --skip-live-units
```

The authenticated browser settings surface also exposes tenant onboarding status and scaffold creation at:

- `http://slack.localhost/settings/tenants`

That page also provides a local credential-install form for the same fields. It posts to the local authenticated API, writes the configured dotenv file, and does not render stored secret values back into the page.
The tenant tiles now refresh in place after onboarding actions, and the manifest section exposes `Copy Manifest JSON` so the rendered manifest can be pasted directly into Slack's app-manifest UI.
The scaffold and credential-install panels are collapsible, so the page stays compact once a step is complete.
After credentials are installed, the tenant tile should show `ready_to_activate`; activation is the explicit step that changes the tenant from disabled to enabled.
Enabled tenant tiles also expose live-sync controls and a bounded backfill button.
The retire control is guarded through a browser modal: type the tenant name to remove the config entry, and optionally check the DB-deletion box to also delete mirrored DB rows for that tenant.

The browser user bootstrap is per-install, not per-workspace.

### Entrypoint rule of thumb

- Before install, run commands from the repo with `uv run slack-mirror ...`.
- After install, use `slack-mirror-user ...` for managed-runtime commands because that wrapper pins the managed config, DB, and cache paths.
- Keep using repo scripts such as `scripts/install_live_mode_systemd_user.sh <workspace>` from a repo checkout unless you have intentionally copied those scripts elsewhere.

## Install

Supported product entrypoint:

```bash
slack-mirror user-env install
```

Script entrypoint:

```bash
scripts/user_env.sh install
```

The script is a compatibility shim that delegates to `slack-mirror user-env`.

This will:
1. copy current repo contents into the app snapshot
2. create/update a dedicated venv
3. install the package into that venv
4. create config from template if missing
5. migrate legacy state from `~/.local/share/slack-mirror/var` if present
6. run `mirror init` (migrations) and `workspaces sync-config`
7. create managed launchers for CLI, API, and MCP entrypoints
8. create and start the managed API service unit
9. run managed-runtime validation for config, DB, workspace sync, the API service, and the managed MCP launcher

This does not install the per-workspace live `webhooks` and `daemon` units. After you install those, use `slack-mirror user-env validate-live` for the full live-service gate.
If you want one unattended operator gate that also checks the managed launchers, MCP health, and API unit file, use `slack-mirror user-env check-live`.

## Update

Supported product entrypoint:

```bash
slack-mirror user-env update
```

Script entrypoint:

```bash
scripts/user_env.sh update
```

The script is a compatibility shim that delegates to `slack-mirror user-env`.

Update preserves:
- `~/.config/slack-mirror/config.yaml`
- `~/.local/state/slack-mirror/slack_mirror.db`
- `~/.local/cache/slack-mirror`
- previous managed app snapshot at `~/.local/share/slack-mirror/app.previous`
- managed launchers are refreshed in place
- `slack-mirror-api.service` is restarted in place
- `slack-mirror-runtime-report.timer` is refreshed and re-enabled in place
- managed-runtime validation is rerun automatically after the update, including the managed MCP health probe

It also saves the latest template to:
- `~/.config/slack-mirror/config.example.latest.yaml`

Use that file to manually merge any newly introduced config keys.

If the updated app snapshot is bad, you can restore the previous one with:

```bash
slack-mirror user-env rollback
```

Rollback restores the previous managed app snapshot and refreshes the venv, wrappers, and API service.
Rollback does not reverse DB schema, queue contents, or other runtime state changes.

Use rollback for bad code/runtime updates, not as a substitute for DB backup and restore.

## Uninstall

Supported product entrypoint:

```bash
slack-mirror user-env uninstall
```

Script entrypoint:

```bash
scripts/user_env.sh uninstall
```

Default uninstall removes app/venv/wrappers/service and keeps config/data.

To purge everything:

```bash
slack-mirror user-env uninstall --purge-data
```

Equivalent script form:

```bash
scripts/user_env.sh uninstall --purge-data
```

The script is a compatibility shim that delegates to `slack-mirror user-env`.
It also removes the API and MCP launchers plus the API service unit.

## Status

Supported product entrypoint:

```bash
slack-mirror user-env status
```

Machine-readable form:

```bash
slack-mirror user-env status --json
```

Script entrypoint:

```bash
scripts/user_env.sh status
```

The script is a compatibility shim that delegates to `slack-mirror user-env`.

Shows wrapper/API/MCP/API service/config/db presence and current live-mode service status.
It also shows whether a rollback snapshot is currently available.
When managed config exists, it now also reports the latest persisted `mirror reconcile-files` summary per workspace, including whether a reconcile state file exists and the last recorded `downloaded` / `warnings` / `failed` counts.

For a shareable runtime snapshot built from the managed API surfaces, use:

```bash
slack-mirror user-env snapshot-report
slack-mirror user-env snapshot-report --name morning-ops --json
python scripts/render_runtime_report.py --base-url http://slack.localhost --format markdown --output /tmp/slack-mirror-runtime-report.md
python scripts/render_runtime_report.py --base-url http://slack.localhost --format html --output /tmp/slack-mirror-runtime-report.html
```

Both consume `/v1/runtime/status` and `/v1/runtime/live-validation` and are useful for periodic ops reports or review handoff.
The supported `user-env snapshot-report` command writes into `~/.local/state/slack-mirror/runtime-reports/` with timestamped files plus stable `*.latest.*` copies. Older timestamped snapshots are pruned automatically; the managed retention policy keeps the most recent 24 snapshot sets or 14 days of history, whichever is smaller.
That same managed snapshot path is also maintained automatically by `slack-mirror-runtime-report.timer`.
The latest managed snapshots are also readable through the local API at `/v1/runtime/reports`, `/v1/runtime/reports/{name}`, `/v1/runtime/reports/latest`, `/runtime/reports`, `/runtime/reports/{name}`, and `/runtime/reports/latest`. The browser index highlights the freshest snapshot, links it through the stable latest alias, and exposes header links for the latest HTML and latest manifest.

## Combined Live Check

Supported product entrypoint:

```bash
slack-mirror user-env check-live
```

Machine-readable form:

```bash
slack-mirror user-env check-live --json
```

This is the one-command operator smoke check. It combines:

- managed runtime artifact presence for the CLI/API/MCP launchers plus the API and runtime-report unit files
- active `slack-mirror-runtime-report.timer` scheduling
- a real MCP stdio health probe through the managed `slack-mirror-mcp` wrapper
- a bounded concurrent MCP readiness probe across multiple simultaneous wrapper launches
- full `validate-live` health checks for config, DB, workspace sync, tokens, units, and queue health

Use this when you want one pass/fail gate for unattended installs and release smoke checks.
It is intentionally stricter than the first `user-env install` validation: a fresh blank install can pass its managed-runtime bootstrap before workspace credentials and live units exist, while `check-live` should continue to fail until workspace configuration and live-mode setup are complete.

`check-live` now also includes the latest persisted `mirror reconcile-files` evidence inside its validation payload, so file-repair regressions show up in the same operator surface as the rest of the managed runtime health checks.

## Live Recovery

Supported product entrypoint:

```bash
slack-mirror user-env recover-live
```

Apply the safe remediations:

```bash
slack-mirror user-env recover-live --apply
```

Machine-readable form:

```bash
slack-mirror user-env recover-live --json
```

This recovery command is intentionally bounded. Safe automatic remediations are limited to:

- refreshing the managed install artifacts with `user-env update` when the managed wrappers or managed runtime-report unit files are missing or when the MCP smoke probe fails
- `systemctl --user daemon-reload`
- restarting the managed API service when its unit exists but is inactive
- restarting the managed workspace live units when their unit files exist but the units are inactive
- re-enabling `slack-mirror-runtime-report.timer` when the timer file exists but the timer is inactive

These remain operator-only and are not auto-applied:

- config or dotenv problems
- missing or unreadable DB state
- missing workspace sync
- missing outbound write tokens
- duplicate topology cleanup
- queue error or backlog remediation beyond restarting the managed units

## Live Validation

Supported product entrypoint:

```bash
slack-mirror user-env validate-live
```

Machine-readable form:

```bash
slack-mirror user-env validate-live --json
```

This checks the supported unattended runtime contract and fails when it finds:

- missing managed config or DB
- enabled workspaces missing from the DB
- missing explicit outbound write tokens
- missing or inactive managed API/webhooks/daemon units
- duplicate legacy `events` or `embeddings` units active alongside the unified daemon
- daemon units that are active in `systemd` but not writing fresh runtime heartbeats

Queue error counts still fail in full live validation when they exceed the live thresholds.
Stale mirrored channels older than the built-in freshness window are now warnings rather than hard failures, because large Slack workspaces naturally contain many quiet historical channels.
Use `mirror status --classify-access` to distinguish inactive-but-mirrored channels from actual ingest regressions.
When full live validation sees no unexpected empty public/private channels, it suppresses `STALE_MIRROR` entirely instead of emitting a low-value warning. This covers both actively moving workspaces and mirrored-but-quiet workspaces like low-traffic project tenants.
The narrower install/update validation gate still treats stale mirror freshness as a warning because live workspace units are not provisioned there.
When a persisted `mirror reconcile-files` state file exists for a workspace, validation also reports the last reconcile batch summary and warns if that batch recorded repair warnings or failures. This keeps hosted-file repair drift visible without turning reconcile history into a hard live-health failure.

The command emits stable issue classes such as:

- `CONFIG_MISSING`
- `DB_MISSING`
- `WORKSPACE_DB_MISSING`
- `OUTBOUND_TOKEN_MISSING`
- `LIVE_UNIT_INACTIVE`
- `DUPLICATE_TOPOLOGY`
- `EVENT_ERRORS`
- `EMBEDDING_ERRORS`
- `EVENT_BACKLOG`
- `EMBEDDING_BACKLOG`
- `STALE_MIRROR`

See [LIVE_MODE.md](/home/ecochran76/workspace.local/slack-export/docs/dev/LIVE_MODE.md) for the recovery flow tied to those classes.
