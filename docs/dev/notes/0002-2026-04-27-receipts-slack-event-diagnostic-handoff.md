# Receipts Slack Event Diagnostic Handoff

Date: 2026-04-27

## Purpose

`../receipts` now has a Slack-only Live View diagnostic lane:

- Receipts calls the Slack adapter `listEvents()` through the child-owned
  `GET /v1/events` route.
- The diagnostic lane runs only when the Receipts Live View source filter is
  explicitly set to Slack.
- Slack is still not counted in `All ready feeds` until Slack advertises event
  descriptors and event status.

Receipts reference:

- `../receipts/docs/dev/plans/0020-2026-04-27-slack-event-diagnostic-lane.md`
- Receipts commit `8605dc9 feat(web): add slack event diagnostic lane`

## What Receipts Observed

Receipts added and validated adapter support against a synthetic Slack event
page. The parent-side code is ready to consume:

```text
GET /v1/events?tenant=...&after=...&limit=...&service_kind=...&account_key=...&event_type=...&privacy=...
```

However, the currently running Slack service at `127.0.0.1:8787` returned:

```json
{
  "ok": false,
  "error": {
    "code": "NOT_FOUND",
    "message": "Unknown path: /v1/events"
  }
}
```

That means the Slack repo has the route in source/planning history, but the
runtime baseline Receipts is pointed at is not yet serving it, or needs to be
rebuilt/reinstalled/restarted from the implementation that includes the route.

## Slack Export Action Items

1. Ensure the deployed/user-scoped Slack Mirror API service includes
   `GET /v1/events`.
2. Restart or reinstall the managed API/runtime service so
   `curl 'http://127.0.0.1:8787/v1/events?tenant=default&limit=1'` returns a
   valid event page rather than `NOT_FOUND`.
3. Confirm `GET /v1/service-profile` advertises:
   - `capabilities.eventCursorRead: true`
   - the event list route/template under child event metadata
   - `capabilities.eventFollow: false` until follow/SSE exists
4. Add the remaining full-readiness surfaces requested in
   `docs/dev/notes/0001-2026-04-27-receipts-live-view-readiness-followup.md`:
   - `capabilities.eventDescriptors: true` with stable descriptors for emitted
     event families
   - `capabilities.eventStatus: true` with a status/watermark route or
     equivalent machine-readable child-owned metadata

## Expected Event Page Contract

Receipts can normalize flexible Slack event rows, but Slack should prefer a
stable shape with:

- `id`
- `event_type`
- `occurred_at`
- `recorded_at`
- `cursor`
- `title`
- `summary`
- `privacy`
- `subject: { id, kind }`
- `source_refs`
- `native_ids`
- optional `payload`

The page should return:

- `events`
- `nextCursor` or `next_cursor`
- `statusText` or `status_text`
- optional `status: "complete" | "partial"`

If no rows match a valid cursor/filter, return an empty successful page, not
`404`.

## Guardrails

- Slack Mirror owns event creation, persistence, ordering, cursor encoding,
  retention, native Slack provenance, and human Slack label resolution.
- Receipts owns the parent Live View UX and parent-side cursor bookmarks.
- Receipts should not parse Slack cursor internals, SQLite offsets, Slack
  timestamps, or local service state to infer readiness.

## Validation Target

Run from the Slack repo/runtime host:

```bash
curl -sS 'http://127.0.0.1:8787/v1/events?tenant=default&limit=1'
curl -sS 'http://127.0.0.1:8787/v1/service-profile'
```

Then verify from Receipts:

```bash
curl -sS 'http://127.0.0.1:5177/api/children/slack/v1/events?tenant=default&limit=1'
```

Browser target: Receipts Live View with source filter `Slack` should show
Slack diagnostic rows or an empty successful diagnostic page. Slack should only
move into `All ready feeds` after descriptors and event status are advertised.

## Status

OPEN. Receipts has the parent diagnostic lane; Slack Export needs to make sure
the running API service includes `/v1/events`, then complete descriptor/status
advertisement for full Live View readiness.
