# Auth Guardrails (Workspace 1 Validation)

This doc captures the expected behavior of auth guardrails in `slack-mirror` and the smoke-test matrix used to validate them.

## Scope

- Prefer bot token by default
- Require explicit `--auth-mode user` for user-token paths
- Support dedicated user-auth message pulls via `--messages-only`

## Preconditions

- `config.local.yaml` includes `dotenv: ~/credentials/API-keys.env`
- `default` workspace token resolves from `SLACK_BOT_TOKEN`
- `SLACK_USER_TOKEN` is present for explicit user-mode tests
- `default.outbound_token` resolves from `SLACK_BOT_TOKEN`
- `default.outbound_user_token` resolves from `SLACK_USER_TOKEN`

## Test Matrix

### 1) Baseline auth verify

```bash
.venv/bin/python -m slack_mirror.cli.main --config config.local.yaml workspaces verify --workspace default
.venv/bin/python -m slack_mirror.cli.main --config config.local.yaml workspaces verify --workspace default --require-explicit-outbound
```

Expected:
- `default ok ok team=<team> user=<bot-user>`
- explicit outbound validation also passes

### 2) Negative guardrail: mismatched mode (bot token + user mode)

```bash
.venv/bin/python -m slack_mirror.cli.main --config config.local.yaml mirror backfill \
  --workspace default --auth-mode user --include-messages --messages-only --channel-limit 1
```

Expected:
- command fails with message like:
  - `detected a bot token, but --auth-mode user was requested`

### 3) Bot-mode smoke (messages-only)

```bash
.venv/bin/python -m slack_mirror.cli.main --config config.local.yaml mirror backfill \
  --workspace default --auth-mode bot --include-messages --messages-only --channel-limit 1
```

Expected:
- command completes successfully
- users/channels bootstrap is skipped (`messages-only` path)

### 4) User-mode smoke (messages-only)

Use a config where `default.token` resolves to `SLACK_USER_TOKEN` (or a temp override), then run:

```bash
.venv/bin/python -m slack_mirror.cli.main --config <user-token-config> mirror backfill \
  --workspace default --auth-mode user --include-messages --messages-only --channel-limit 1
```

Expected:
- command completes successfully
- at least one channel/message may be fetched depending on token scope/history

## Regression Notes

- Avoid nested env fallback syntax like `${A:-${B:-}}` in config values.
- Use single-level interpolation only (e.g., `${SLACK_BOT_TOKEN:-}`).
- Dotenv loading should occur before interpolation.
