# 0154 | Receipts Runtime API Pause Decision

State: CLOSED

Roadmap: P04

## Context

Receipts left a runtime API pause handoff in:

- `docs/dev/notes/0011-2026-05-02-receipts-runtime-api-pause-handoff.md`
- `../receipts/docs/dev/notes/0026-2026-05-02-slack-runtime-api-pause-decision.md`

Receipts currently exposes `start`, `stop`, `restart`, and `pause` for the
configured local unit `slack-mirror-api.service`. Its `pause` action is mapped
to `systemctl --user stop slack-mirror-api.service`.

## Decision

Slack Export should not define a distinct first-class API pause/suspend
semantic yet.

The supported child-owned operator semantics remain:

- start the managed API unit
- stop the managed API unit
- restart the managed API unit
- read runtime status and validation

The existing internal migration helper that pauses managed runtime units is not
an operator-visible paused state. It temporarily stops active units around
schema migrations and restores the previously active units afterward.

## Receipts Guidance

Receipts may continue to label `pause` as an alias for stopping
`slack-mirror-api.service`, provided it does not persist or display that as a
distinct Slack-owned paused state.

If Slack Export later adds a real pause/suspend contract, that future slice must
define:

- API route or CLI command
- scope: API only, tenant live units, or whole managed runtime
- enablement behavior across boot/session restart
- status fields that distinguish paused from inactive/stopped
- safe response fields Receipts may persist and display

## Validation

Documentation-only decision. No runtime code or managed units were changed.
