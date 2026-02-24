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
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-messages --oldest 1700000000.000000 --latest 1800000000.000000
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-files --cache-root ./cache
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-files --file-types all --cache-root ./cache
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-files --download-content --cache-root ./cache
python -m slack_mirror.cli.main channels sync-from-tool
python -m slack_mirror.cli.main search reindex-keyword --workspace default
python -m slack_mirror.cli.main search keyword --workspace default --query deploy --limit 20
python -m slack_mirror.cli.main search keyword --workspace default --query "deploy from:<@U123> channel:<#C123> has:link -draft after:1700000000"
python -m slack_mirror.cli.main docs generate --format markdown --output docs/CLI.md
python -m slack_mirror.cli.main docs generate --format man --output docs/slack-mirror.1
python scripts/check_generated_docs.py

# after install (entrypoint)
slack-mirror --config config.yaml mirror init

# webhook service
python -m slack_mirror.cli.main --config config.yaml mirror serve-webhooks --workspace default --bind 127.0.0.1 --port 8787
python -m slack_mirror.cli.main --config config.yaml mirror process-events --workspace default --limit 200
python -m slack_mirror.cli.main --config config.yaml mirror process-events --workspace default --loop --interval 2 --max-cycles 10

# shell completion scripts
python -m slack_mirror.cli.main completion print bash > /tmp/slack-mirror.bash
python -m slack_mirror.cli.main completion print zsh > /tmp/_slack-mirror
```

> Note: This is scaffold-level documentation during Phase A. Behavior and command names may evolve.
