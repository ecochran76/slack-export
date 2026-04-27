# 0127 | Receipts live view readiness

State: CLOSED

Roadmap: P12

## Purpose

Complete the Slack Mirror side of Receipts Live View readiness after the first
cursor-read event surface landed under `0126`.

Receipts now gates a child source as Live View ready only when the child
service profile advertises:

- cursor-backed event reads
- stable event descriptors
- child-owned event status or watermark metadata

## Current State

Slack Mirror source already exposes `GET /v1/events` and advertises
`capabilities.eventCursorRead: true`.

The managed API runtime was stale on 2026-04-27 and returned `NOT_FOUND` for
`/v1/events` until the user-scoped editable install was refreshed and
`slack-mirror-api.service` was restarted.

Remaining source work:

- advertise `capabilities.eventDescriptors: true`
- advertise `capabilities.eventStatus: true`
- expose stable descriptors for the current event families
- expose a status route with latest cursor/watermark metadata
- keep `capabilities.eventFollow: false` until a streaming/follow route exists

## Scope

- Add descriptor metadata for:
  - `slack.message.observed`
  - `slack.thread_reply.observed`
  - `slack.file.linked`
  - `slack.export.created`
- Add `GET /v1/events/status` over the same child-owned event source as
  `GET /v1/events`.
- Preserve existing camelCase event fields while adding snake_case aliases for
  parent UX compatibility.
- Update the service profile, API contract docs, roadmap, and runbook.

## Non-goals

- Do not add event follow, SSE, websocket, or streaming semantics in this
  slice.
- Do not move cursor ownership or ordering into Receipts.
- Do not expose raw Slack websocket/webhook transport events as product events.
- Do not extract shared libraries before the convergence gate is met.

## Acceptance

- `GET /v1/service-profile` advertises `eventCursorRead`, `eventDescriptors`,
  `eventStatus`, and `eventFollow: false`.
- `GET /v1/events/status` returns child-owned `event_count`,
  `latest_cursor`, and per-event-type watermarks.
- `GET /v1/events` rows carry both the existing camelCase fields and stable
  snake_case aliases for event type, timestamps, account key, service kind,
  source refs, and native ids.
- Targeted service/API tests pass.
- Managed runtime is refreshed and restarted after source changes.

## Status

CLOSED. Slack Mirror now advertises event descriptors and event status,
exposes `GET /v1/events/status`, preserves existing camelCase event rows while
adding snake_case aliases, and refreshes the managed runtime after source
changes.
