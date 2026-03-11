# Semi-Permanent Test Database Setup

Goal: keep a reusable, hydrated **repo-local test database** for semantic testing without committing runtime state to git.

This is intentionally for local dev/test. It is **not** the recommended long-term runtime location for user installs or daily briefing automation.

## Canonical repo-local test paths (gitignored)

- Config: `config.local.yaml`
- DB: `.local/state/slack_mirror_test.db`
- Cache: `.local/cache`

## One-time setup

```bash
cp config.example.yaml config.local.yaml
```

Then set these in `config.local.yaml`:

- `storage.db_path: ./.local/state/slack_mirror_test.db`
- `storage.cache_root: ./.local/cache`
- workspace token/signing settings for your test workspace

## Initialize + hydrate

```bash
slack-mirror --config config.local.yaml mirror init
slack-mirror --config config.local.yaml workspaces sync-config

# Full hydration (bot token)
slack-mirror --config config.local.yaml mirror backfill \
  --workspace default \
  --auth-mode bot \
  --include-messages \
  --include-files
```

For user-token targeted hydration:

```bash
slack-mirror --config config.local.yaml mirror backfill \
  --workspace default \
  --auth-mode user \
  --include-messages \
  --messages-only \
  --channels C123,C456
```

## Keep embeddings fresh

```bash
slack-mirror --config config.local.yaml mirror process-embedding-jobs --workspace default --limit 5000
```

## Semantic smoke tests

```bash
slack-mirror --config config.local.yaml search semantic \
  --workspace default \
  --query "deployment failure in release pipeline" \
  --limit 10

slack-mirror --config config.local.yaml search keyword \
  --workspace default \
  --query "deployment failure in release pipeline" \
  --mode hybrid \
  --limit 10
```

## Notes for first-user install handoff

- This DB is a **test artifact**, not guaranteed forward-compatible across major schema changes.
- Before handing off, run migrations from the target build and verify search commands against that binary.
- Keep runtime DB outside git (`.local/` and `data/` are ignored).
