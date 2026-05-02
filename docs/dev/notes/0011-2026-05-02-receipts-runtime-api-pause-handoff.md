# Note 0011 | Receipts Runtime API Pause Handoff

Date: 2026-05-02

## From Receipts

Receipts added a Slack API settings control surface for the managed API unit.
The parent-owned route is:

- `GET /api/receipts/slack/runtime-api`
- `POST /api/receipts/slack/runtime-api`

It controls only the configured local unit:

- `slack-mirror-api.service`

Actions currently exposed by Receipts:

- `start`
- `stop`
- `restart`
- `pause`

## Current Pause Mapping

Receipts maps `pause` to:

```bash
systemctl --user stop slack-mirror-api.service
```

This is an alias, not a new Slack Export runtime semantic.

The reason is that Slack Export currently has public/runtime unit controls for
start, stop, and restart. The internal migration helper named
`_pause_managed_runtime_for_migrations` stops active managed units before schema
migrations and restores them afterward, but it does not define a durable
operator-visible paused state.

## Homework For Slack Export

Please decide whether Slack Export wants a first-class pause/suspend contract
that is distinct from stopping the API service.

If yes, please define:

- route or CLI command Receipts should call;
- whether pause applies to API only, tenant live units only, or the whole managed
  runtime;
- whether paused units stay enabled for future boot;
- status fields that distinguish `paused` from `inactive` or `stopped`;
- response envelope and safe-to-persist fields.

Until Slack Export defines that, Receipts will keep `pause` as a UI alias for
stopping the API unit and will continue to document the alias.

## Receipts Validation Evidence

Receipts validated the current bridge with:

- `npm run build:web`
- `npm run smoke:reports-guest-links -- --skip-build`
- `python scripts/validate_repo.py`
- dry-run status/restart/pause curls against
  `/api/receipts/slack/runtime-api`
