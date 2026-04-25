# 0124 | Receipts context window handoff

State: CLOSED

Roadmap: P12

## Purpose

Receipts now has a shared context-window contract for opening a search result as
a scrollable evidence stream. Slack Mirror should keep owning Slack retrieval
and projection logic while exposing enough child-owned context paging for
Receipts to render the selected message in its surrounding channel or thread.

Canonical Receipts plan:
`../receipts/docs/dev/plans/0005-2026-04-25-context-window-contract.md`

## Current State

Receipts currently renders a stream-style evidence drawer from already-loaded
search/evidence details. Earlier/later controls are parent-side reveal controls
only; they are not backed by a Slack-owned context paging route yet.

Slack Mirror now exposes `GET /v1/context-window` for selected Slack message
`action_target.id` values. The route returns a Receipts-compatible context
window with Slack-owned opaque cursors, channel/thread stream identity, human
channel/sender labels, selected-item metadata, native Slack IDs, artifact refs,
and page-info cursors for earlier/later navigation.

## Requested Slack Mirror Work

- Add a cursor-backed context route for Receipts, preferably:
  - `GET /v1/context-window?result_id=<id>&direction=<around|before|after>&cursor=<opaque>&limit=<n>`
- Equivalent Slack-specific route naming is acceptable if the service profile
  advertises the route template.
- Support:
  - `direction=around`: return a window containing the selected result
  - `direction=before`: return earlier messages before the opaque cursor
  - `direction=after`: return later messages after the opaque cursor
- Treat cursors as Slack Mirror-owned opaque tokens. Receipts must not parse
  Slack timestamps, thread positions, or SQLite offsets.
- Mark `capabilities.contextWindow: true` in `GET /v1/service-profile` only
  after the route is implemented and covered.

## Response Shape To Map

The response should map cleanly to Receipts' `ReceiptsContextWindow`:

- `service`: `slack`
- `resultId`
- `streamId`: stable channel or thread stream identifier
- `streamLabel`: human label such as `#channel` or `#channel / thread`
- `streamKind`: `slack-channel` or `slack-thread`
- `tenantLabel`: workspace/team label when known
- `scopeLabel`: workspace or export scope label when useful
- `selectedItemId`
- `items[]`: timestamped Slack messages with human sender labels, body text,
  native IDs, source refs, artifacts, and Slack-specific extensions
- `pageInfo`: `hasBefore`, `hasAfter`, `beforeCursor`, `afterCursor`

## Slack Evidence To Preserve

Keep native Slack provenance separate from display text:

- workspace/team ID and name when available
- channel ID and channel name
- message `ts`
- thread root `ts`
- user ID plus human-facing `user_label` / display name fields
- permalink, file, canvas, and attachment refs when present
- existing `action_target` or result target metadata

## Guardrails

- Do not move Slack search, channel/day JSON, thread reconstruction, export
  rendering, or report generation into Receipts for this slice.
- Do not make Receipts parse Slack-native identifiers to page context.
- Preserve native IDs under provenance fields instead of displaying them as
  sender/channel labels.
- Keep the route usable by the Receipts BFF through existing trusted-local or
  child-session auth.

## Suggested Validation

- Unit coverage for around/before/after paging on channel messages.
- Unit coverage for thread-focused windows if Slack Mirror can distinguish the
  selected result as thread-scoped.
- API test proving cursors are opaque and stable enough for adjacent page
  navigation.
- Service profile test showing `contextWindow: true` and the route template
  only once the route exists.
- Live Receipts smoke: click a Slack search result, open the stream drawer,
  page earlier and later, and verify human sender/channel labels render.

## Status

CLOSED. Slack Mirror owns the implemented context-window route and advertises
`capabilities.contextWindow: true` plus the route template from
`GET /v1/service-profile`.
