# 0153 | Receipts Full Event Stream

State: OPEN

Roadmap: P12

## Current State

Slack Mirror exposes `GET /v1/events` and `GET /v1/events/status` as
cursor-backed read surfaces over committed Slack product events derived from
durable mirrored state. The shipped event families cover messages, thread
replies, linked files, and managed export lifecycle events. The service profile
correctly advertises `eventCursorRead: true`, `eventDescriptors: true`,
`eventStatus: true`, and `eventFollow: false`.

Receipts is the parent UX owner for watching the full event stream and managing
subscriber filters. Slack Mirror remains the child owner for Slack event
capture, redaction, event identity, cursor semantics, and native Slack filters.

## Scope

- Add a Receipts-grade filter vocabulary to Slack-owned event read/status
  surfaces.
- Keep current event-follow capability disabled until Slack Mirror has a real
  append-only event journal and live stream endpoint.
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
- `/v1/service-profile` route templates advertise the filter vocabulary while
  keeping `eventFollow: false`.
- `docs/API_MCP_CONTRACT.md` records the Receipts/Slack ownership split and the
  append-only journal requirement for full-stream subscriptions.

## Remaining Work

- Add a durable append-only event journal owned by `slack_mirror.service` or
  `slack_mirror.sync`.
- Emit journal rows for message creates, edits, deletes, thread replies,
  reactions, channel membership changes, user/profile status changes where
  Slack Mirror has source events, outbound write results, and sync/runtime
  status changes.
- Add a stream/follow API, likely SSE or bounded long-poll first, and only then
  flip `capabilities.eventFollow` to true.
- Add subscription-focused smoke tests that model Receipts filters such as
  "reactions from Michael on default" and "status changes from Baker on
  SoyLei".

## Definition Of Done

- The read/status filter slice is implemented and covered by targeted tests.
- The live-follow gap remains explicit in docs and service profile capability
  metadata.
- The next slice can start from a concrete append-only event-journal plan rather
  than rediscovering current limitations.
