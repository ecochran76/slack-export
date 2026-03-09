# Dedicated Slack Mirror Socket Mode App

Use a **separate Slack app** for Slack Mirror.
Do **not** share the same Slack app with OpenClaw if you want both systems to receive live events reliably.

## Why

When two consumers share one Slack app:

- **HTTP Events API** can only point at one request URL at a time.
- **Socket Mode** can distribute events across multiple active connections for the same app.

That means OpenClaw and Slack Mirror can compete for the same live event stream.

## Recommended setup

- **OpenClaw app** → assistant / chat handling
- **Slack Mirror app** → archival / search / export

## Manifest files

- OAuth-capable template: `manifests/slack-mirror-socket-mode.yaml`
- No-OAuth/private variant: `manifests/slack-mirror-socket-mode-nooauth.yaml`

Both enable:

- `socket_mode_enabled: true`
- message subscriptions for:
  - `message.channels`
  - `message.groups`
  - `message.im`
  - `message.mpim`

## Tokens you need from the dedicated Slack Mirror app

After creating/installing the dedicated app, collect:

- Bot token: `xoxb-...`
- User token: `xoxp-...` (if you use user-auth catch-up/backfill)
- App token: `xapp-...` with Socket Mode enabled
- Signing secret (optional if you keep webhook support around, not needed for pure Socket Mode)

## Suggested env vars

Keep these separate from OpenClaw's Slack app credentials.

```bash
SLACK_MIRROR_BOT_TOKEN=...
SLACK_MIRROR_USER_TOKEN=...
SLACK_MIRROR_APP_TOKEN=...
SLACK_MIRROR_SIGNING_SECRET=...

SLACK_MIRROR_BOT_TOKEN_SOYLEI=...
SLACK_MIRROR_USER_TOKEN_SOYLEI=...
SLACK_MIRROR_APP_TOKEN_SOYLEI=...
SLACK_MIRROR_SIGNING_SECRET_SOYLEI=...
```

## Next config step

Once the dedicated app exists, point `config.local.yaml` at the dedicated Slack Mirror env vars instead of the shared app vars.
