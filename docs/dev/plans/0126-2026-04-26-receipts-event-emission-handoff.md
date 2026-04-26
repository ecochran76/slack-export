# 0126 | Receipts event emission handoff

State: OPEN

Roadmap: P12

## Purpose

Receipts now consumes imcli committed product events through a cursor-backed
child API. Slack Mirror should add a comparable child-owned event emission
surface so Receipts can eventually show one cross-child activity stream without
reading Slack-native database tables or private service logs.

Receipts plan:
`../receipts/docs/dev/plans/0007-2026-04-26-child-event-consumption.md`

Receipts commits:
- `7eb6f9e feat(web): add IM event activity`
- follow-on local slice adds parent-side opaque event cursor storage at
  `GET/POST /api/receipts/event-cursors`

## Current State

Receipts has an IM-first `ReceiptsChildEvent` view model and dashboard activity
panel. It reads imcli events through:

```text
GET /api/children/im/v1/events
```

Receipts stores only the last-read cursor per child service, tenant, provider,
account, and event type. Cursor values are opaque to Receipts and remain
child-owned.

## Requested Slack Mirror Work

Add a Slack-owned committed event read surface modeled on the imcli pattern:

```text
GET /v1/events?tenant=...&after=...&limit=...&service_kind=...&account_key=...&event_type=...&privacy=...
```

The route should return a stable page with:

- `events`: committed product events, not provider transport noise;
- `nextCursor`: Slack-owned opaque cursor for the next read;
- status metadata that distinguishes complete, partial, and failed reads.

Advertise support from `GET /v1/service-profile`:

- `capabilities.eventCursorRead: true`
- `capabilities.eventFollow: true` only when a follow/SSE/streaming surface is
  ready
- route templates for event list/follow if the profile schema supports them

## Event Families

Start with durable events that matter to report/search/evidence workflows:

- Slack message observed or updated
- Slack file attachment observed, downloaded, previewed, or linked
- reaction added or removed
- thread reply observed
- channel membership or channel metadata changed when it affects evidence labels
- managed export/report artifact created, renamed, opened, or deleted
- sync/index lifecycle checkpoints that are useful to an operator without
  exposing local-private implementation details

Avoid exposing raw websocket/webhook delivery events as the primary product
surface. Those can remain service logs or local-private diagnostic events.

## Receipts Event Mapping

Each event should map cleanly to Receipts fields:

- stable child event id
- event type string
- subject id and kind
- occurred/recorded timestamps
- cursor
- human-readable title and summary
- child service kind, account/workspace key, tenant
- privacy class: `public`, `user`, `superuser`, or `local-private`
- native Slack provenance under machine-readable refs/ids
- optional payload with redacted details appropriate for the privacy class

Human-facing labels should be resolved before the event reaches Receipts where
Slack Mirror already owns the user/channel profile tables. Preserve native
Slack IDs separately for provenance.

## Guardrails

- Slack Mirror owns Slack event creation, persistence, ordering, retention, and
  cursor encoding.
- Receipts must not parse Slack database internals or event cursor internals.
- Do not expose local-private auth, token, cookie, or filesystem events to
  ordinary users or guests.
- Keep event emission separate from report artifact payloads; events can point
  to artifacts but should not duplicate full report contents.

## Suggested Validation

- Unit/API tests proving `GET /v1/events` pages committed events with opaque
  cursors.
- Tests for event type, provider/account, privacy, and limit filters.
- Service-profile test proving `eventCursorRead` advertises only when the route
  is wired.
- Receipts smoke after integration: event page read through
  `/api/children/slack/v1/events`, cursor persistence in Receipts, and no
  local-private event leakage to guest/user mode.

## Status

OPEN. Implementation remains owned by Slack Mirror. Receipts only owns the
shared frontend contract and parent-side cursor bookmark.
