# User-Scope Install / Update / Uninstall

This installs `slack-mirror` into an isolated user-owned runtime that is independent of your git checkout.

## What it sets up

- App snapshot: `~/.local/share/slack-mirror/app`
- Virtualenv: `~/.local/share/slack-mirror/venv`
- Runtime state: `~/.local/state/slack-mirror`
  - DB: `~/.local/state/slack-mirror/slack_mirror.db`
- Runtime cache: `~/.local/cache/slack-mirror`
- Config: `~/.config/slack-mirror/config.yaml`
- Wrapper CLI: `~/.local/bin/slack-mirror-user`
- API launcher: `~/.local/bin/slack-mirror-api`
- MCP launcher: `~/.local/bin/slack-mirror-mcp`
- API service: `~/.config/systemd/user/slack-mirror-api.service`

The wrapper injects env vars for DB/cache and always points to the user config path.
The API launcher runs `slack-mirror api serve` with the managed config.
The MCP launcher runs `slack-mirror mcp serve` with the managed config.
The API service runs the API launcher under `systemd --user`.

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
9. run managed-runtime validation for config, DB, workspace sync, and the API service

This does not install the per-workspace live `webhooks` and `daemon` units. After you install those, use `slack-mirror user-env validate-live` for the full live-service gate.

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
- managed launchers are refreshed in place
- `slack-mirror-api.service` is restarted in place
- managed-runtime validation is rerun automatically after the update

It also saves the latest template to:
- `~/.config/slack-mirror/config.example.latest.yaml`

Use that file to manually merge any newly introduced config keys.

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

Queue error counts are reported as warnings so the command can distinguish broken topology from recoverable backlog or historical failures.

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

See [LIVE_MODE.md](/home/ecochran76/workspace.local/slack-export/docs/dev/LIVE_MODE.md) for the recovery flow tied to those classes.
