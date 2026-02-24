# Configuration (Preview)

`slack-mirror` uses YAML configuration with environment variable interpolation.

## Example

Copy `config.example.yaml` to `config.yaml` and set environment vars.

```yaml
version: 1
storage:
  db_path: ${SLACK_MIRROR_DB:-./data/slack_mirror.db}
  cache_root: ${SLACK_MIRROR_CACHE:-./cache}

workspaces:
  - name: default
    team_id: ${SLACK_TEAM_ID:-}
    token: ${SLACK_TOKEN:-}
    signing_secret: ${SLACK_SIGNING_SECRET:-}
    enabled: true
```

## Interpolation syntax

- `${VAR}` → required env var (empty if not set)
- `${VAR:-fallback}` → env var with default fallback

## Commands (scaffold)

```bash
python -m slack_mirror.cli.main --config config.yaml mirror init
python -m slack_mirror.cli.main --config config.yaml workspaces sync-config
python -m slack_mirror.cli.main --config config.yaml workspaces verify
python -m slack_mirror.cli.main --config config.yaml workspaces list
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-messages --channel-limit 5
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-files --cache-root ./cache
python -m slack_mirror.cli.main channels sync-from-tool

# after install (entrypoint)
slack-mirror --config config.yaml mirror init
```

> Note: This is scaffold-level documentation during Phase A. Behavior and command names may evolve.
