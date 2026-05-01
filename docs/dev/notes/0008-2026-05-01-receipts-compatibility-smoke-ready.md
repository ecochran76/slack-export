# 0008 | Receipts compatibility smoke gate ready

Date: 2026-05-01
From: Slack Export / Slack Mirror
Audience: Receipts maintainers

## Context

Slack Export completed Receipts homework H1 from
`docs/dev/notes/0007-2026-05-01-receipts-dev-state-homework.md`.

Implementation commit:

- `b58bc25 test(receipts): add compatibility smoke gate`

## Command

Default fixture-backed gate:

```bash
python scripts/smoke_receipts_compatibility.py --json
```

Optional live child-service gate:

```bash
python scripts/smoke_receipts_compatibility.py --base-url http://127.0.0.1:8787 --query "website service" --json
```

The live mode uses child-session auth from
`SLACK_MIRROR_FRONTEND_USERNAME` and `SLACK_MIRROR_FRONTEND_PASSWORD` unless
explicit `--username` and `--password` values are supplied.

## Coverage

The gate verifies:

- `GET /v1/service-profile`
- `GET /v1/events`
- `GET /v1/events/status`
- `GET /v1/context-window`
- selected-result export create/open
- allowed guest-grant artifact read
- denied guest-grant access to search, export list, and export mutation routes

## Validation Evidence

Passed in Slack Export:

- fixture mode returned `ok: true`
- live mode against `http://127.0.0.1:8787` returned `ok: true`
- planning audit returned `ok: true`
- `git diff --check`

## Next Recommended Action

Receipts should call this Slack-owned gate from its Slack compatibility
checklist before enabling new parent-side Slack search, report, guest-link, or
live-view behavior.
