# Receipts Live View Readiness Follow-up

Date: 2026-04-27

## Purpose

`../receipts` now has a Live View readiness checklist and a copyable handoff
note generated from child-service profiles.

Receipts references:

- `../receipts/docs/dev/plans/0017-2026-04-27-live-view-readiness-checklist.md`
- `../receipts/docs/dev/plans/0018-2026-04-27-live-view-readiness-export.md`
- commit `827f899 feat(web): copy live readiness note`

This note records the Slack Mirror follow-up needed for Receipts to treat Slack
as a fully live-ready child in the parent Live View UI.

## Current Slack State

Slack Mirror already implemented the important first step:

- `GET /v1/events` returns cursor-backed committed Slack product events.
- `GET /v1/service-profile` advertises `capabilities.eventCursorRead: true`.
- The event cursor is Slack-owned and opaque to Receipts.
- `capabilities.eventFollow` remains false, which is correct until a
  follow/SSE/streaming surface exists.

That means this is not a request to rebuild Slack event emission from scratch.
The remaining work is readiness-profile alignment for the parent UX.

## Receipts Readiness Gate

Receipts currently treats a child as Live View ready only when the child profile
advertises all three of these surfaces:

- `eventCursorRead`
- `eventDescriptors`
- `eventStatus`

The copied readiness note in Receipts also expects the child profile to expose
event route, cursor, descriptor, and status metadata in a machine-readable
shape so the parent UI does not hard-code Slack-specific event families.

## Requested Slack Follow-up

Add or align the Slack child-service profile so Receipts can discover:

1. Event descriptors
   - advertise `capabilities.eventDescriptors: true`
   - expose descriptor metadata for currently emitted event types:
     - `slack.message.observed`
     - `slack.thread_reply.observed`
     - `slack.file.linked`
     - `slack.export.created`
   - include display labels, privacy class, payload stability, redaction, and
     safe-for-role hints where the profile schema supports them

2. Event status
   - advertise `capabilities.eventStatus: true` only when a status route or
     equivalent profile-backed watermark is available
   - expose latest known sequence/cursor/timestamp metadata without requiring
     Receipts to parse Slack cursor internals
   - distinguish no-events, partial, stale, and failed status where practical

3. Route/profile shape
   - keep `GET /v1/events` as the child-owned event page route
   - add a status route such as `GET /v1/events/status` if that is cleaner than
     embedding status metadata in the profile
   - keep follow/SSE unadvertised until it exists

## Guardrails

- Slack Mirror owns event creation, ordering, retention, native Slack
  provenance, label resolution, and cursor encoding.
- Receipts owns the shared Live View UX and parent-side cursor bookmarks.
- Receipts must not parse Slack timestamps, channel IDs, SQLite offsets, event
  cursor internals, or local runtime state to determine readiness.
- Human-readable user/channel labels should remain Slack-owned; native IDs
  should stay present separately for provenance.

## Suggested Validation

- Service-profile test proving `eventCursorRead`, `eventDescriptors`, and
  `eventStatus` advertise accurately.
- Descriptor test proving all emitted event families have stable labels and
  privacy/redaction metadata.
- Event-status API/profile test proving Receipts can read a watermark without
  parsing cursors.
- Receipts smoke after integration: Slack appears as live-ready in Live View
  and event reads succeed through `/api/children/slack/v1/events`.

## Status

OPEN. Slack event cursor reads exist; descriptor and status readiness remain
the follow-up surfaces needed by Receipts Live View.
