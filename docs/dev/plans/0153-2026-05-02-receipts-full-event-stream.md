# 0153 | Receipts Full Event Stream

State: OPEN

Roadmap: P12

## Current State

Slack Mirror exposes `GET /v1/events` and `GET /v1/events/status` as
cursor-backed read surfaces over committed Slack product events derived from
durable mirrored state. The shipped event families cover messages, thread
replies, linked files, and managed export lifecycle events. The service profile
correctly advertises `eventCursorRead: true`, `eventDescriptors: true`,
`eventStatus: true`, and `eventFollow: true`.

The first Receipts-grade filter slice is shipped: event reads and status now
accept actor, actor user id, channel, channel id, subject kind, and subject id
filters, and message/thread rows expose actor aliases where Slack Mirror has
sender provenance.

The first append-only journal slice is shipped: live-intake processing now
records committed child events for message creates, thread-reply creates,
message changes, message deletes, reaction add/remove events, channel member
join/leave events, and user/profile status changes when Slack Mirror receives
the corresponding Slack event.

The first follow slice is shipped: `/v1/events/follow` exposes bounded long-poll
JSON over the append-only child event journal, and `/v1/service-profile`
advertises `eventFollow: true` with the follow route template. Follow does not
replay derived current-state rows such as `slack.message.observed`.

The first operational journal slice is shipped: outbound message/reply write
results and tenant live-sync/backfill requests now emit append-only journal
rows so Receipts subscriptions can observe child-owned operational state
changes without scraping logs or tenant tiles.

Receipts is the parent UX owner for watching the full event stream and managing
subscriber filters. Slack Mirror remains the child owner for Slack event
capture, redaction, event identity, cursor semantics, and native Slack filters.

## Scope

- Add a Receipts-grade filter vocabulary to Slack-owned event read/status
  surfaces.
- Keep event-follow backed by the append-only event journal instead of derived
  current-state rows.
- Define the remaining event families needed for subscriptions such as
  reactions from a named actor on one tenant or status changes from a named
  actor on another tenant.

## Non-Goals

- Do not make Receipts own Slack-native event capture.
- Do not advertise `eventFollow` before a dedicated follow/SSE/streaming route
  exists.
- Do not treat current-state-derived reads as lossless live subscription
  history.
- Do not expose raw private Slack webhook/socket payloads to parent UX layers.

## Acceptance Criteria

- `/v1/events` accepts actor, native actor id, channel, native channel id,
  subject kind, and subject id filters.
- `/v1/events/status` accepts the same filters and reports filtered counts and
  watermarks.
- Event rows expose stable actor aliases for message/thread events where Slack
  Mirror has sender provenance.
- `/v1/service-profile` route templates advertise the filter vocabulary and the
  bounded follow route.
- `docs/API_MCP_CONTRACT.md` records the Receipts/Slack ownership split and the
  append-only journal requirement for full-stream subscriptions.

## Remaining Work

- Backfill existing raw Slack event rows into the child event journal if older
  live-intake events need to appear in Receipts.
- Emit journal rows for richer Slack channel lifecycle events.
- Decide later whether SSE adds enough value beyond bounded long-poll to justify
  an additional transport.
- Add subscription-focused smoke tests that model Receipts filters such as
  "reactions from Michael on default" and "status changes from Baker on
  SoyLei".

## Definition Of Done

- The read/status filter slice is implemented and covered by targeted tests.
- The append-only journal slice is implemented and covered by targeted tests.
- The bounded long-poll follow slice is implemented, covered by targeted tests,
  and deployed to the managed local API.
- Remaining event-family and optional-SSE gaps remain explicit in docs and
  service profile metadata.
