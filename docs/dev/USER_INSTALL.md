# User-Scope Install / Update / Uninstall

This installs `slack-mirror` into an isolated user-owned runtime that is independent of your git checkout.

## What it sets up

- App snapshot: `~/.local/share/slack-mirror/app`
- Virtualenv: `~/.local/share/slack-mirror/venv`
- Runtime data: `~/.local/share/slack-mirror/var`
  - DB: `~/.local/share/slack-mirror/var/slack_mirror.db`
  - Cache: `~/.local/share/slack-mirror/var/cache`
- Config: `~/.config/slack-mirror/config.yaml`
- Wrapper CLI: `~/.local/bin/slack-mirror-user`

The wrapper injects env vars for DB/cache and always points to the user config path.

## Install

```bash
scripts/user_env.sh install
```

This will:
1. copy current repo contents into the app snapshot
2. create/update a dedicated venv
3. install the package into that venv
4. create config from template if missing
5. run `mirror init` (migrations) and `workspaces sync-config`

## Update

```bash
scripts/user_env.sh update
```

Update preserves:
- `~/.config/slack-mirror/config.yaml`
- `~/.local/share/slack-mirror/var/slack_mirror.db`
- `~/.local/share/slack-mirror/var/cache`

It also saves the latest template to:
- `~/.config/slack-mirror/config.example.latest.yaml`

Use that file to manually merge any newly introduced config keys.

## Uninstall

```bash
scripts/user_env.sh uninstall
```

Default uninstall removes app/venv/wrapper and keeps config/data.

To purge everything:

```bash
scripts/user_env.sh uninstall --purge-data
```

## Status

```bash
scripts/user_env.sh status
```

Shows wrapper/config/db presence and current live-mode service status.
