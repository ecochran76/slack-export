# 0007 | Receipts development-state homework

Date: 2026-05-01
From: `../receipts`
Audience: Slack Export / Slack Mirror maintainers
Status: OPEN

## Context

Receipts is now the shared user-facing frontend, search workbench, evidence
inspector, guest-link, report, and live-view layer for Slack Export, Ragmail,
and imcli. Slack Export is the furthest-ahead child service for report/export
behavior and should remain the strongest reference implementation, while still
owning Slack-native runtime, storage, sync, search, and tenant maintenance.

Current Slack Export state is strong for Receipts:

- `GET /v1/service-profile` advertises auth, search, evidence, context window,
  selected-result export, artifact, guest-grant, event, source metadata, and UI
  capabilities.
- `GET /v1/events` and `GET /v1/events/status` expose cursor-backed,
  child-owned event reads and readiness metadata.
- `GET /v1/context-window` gives Receipts a Slack-owned stream view for a
  selected result without forcing the parent to parse Slack timestamps,
  channel IDs, or thread roots.
- Selected-result export bundles provide neutral JSON plus human HTML reports.
- Guest-grant assertion support is constrained to artifact/report reads, with
  search/list/mutation routes kept child-session only.
- Recent guest-preview work renders Slack mentions into guest-safe display
  labels while preserving raw Slack text/provenance separately.

The remaining work is compatibility hardening, event/report coverage, and
operator API polish so Receipts can build a compact, shared frontend without
embedding Slack-specific assumptions.

## Homework

### H1. Add a Receipts compatibility smoke gate

Create one Slack-owned validation command or script that a Receipts maintainer
can run before parent integration work. It should verify the public
Receipts-facing contract without depending on private corpus contents.

Minimum coverage:

- `GET /v1/service-profile`
- `GET /v1/events`
- `GET /v1/events/status`
- `GET /v1/context-window` against a fixture or seeded message result
- selected-result export creation and artifact open
- guest-grant route-policy behavior for allowed artifact reads and denied
  search/list/mutation routes

Acceptance target:

- A single documented command returns structured pass/fail output suitable for
  a runbook entry.
- The command can run against test fixtures and, optionally, a configured live
  local API.
- Failures identify whether the break is profile, events, context, artifact, or
  guest-grant related.

### H2. Treat `/v1/service-profile` as the contract authority

Keep the service profile snapshot stable and complete enough that Receipts can
use it for UI routing and feature gating.

Add or tighten tests for:

- route templates required by Receipts
- `guestGrants.routes`, `localOnlyRoutes`, signature modes, and target kinds
- `events`, `eventDescriptors`, `eventStatus`, and `eventFollow`
- `sourceMetadata.labelFields` versus `sourceMetadata.nativeRefs`
- UI flags that distinguish child-owned tenant/settings controls from
  parent-owned search/report UX

Acceptance target:

- Any Receipts-facing profile drift is caught by tests before release.
- The profile does not advertise experimental browser pages as durable parent
  integration targets until they are production-ready.

### H3. Deepen event readiness for Receipts Live View

Slack Export already emits committed product events. The next useful layer is
maintenance-grade event status that behaves like an operational contract, not
only a list endpoint.

Requested improvements:

- Document cursor retention and stale-cursor behavior.
- Expose explicit status fields for newest available cursor, oldest available
  cursor when known, event family counts, partial/degraded state, and child
  recovery guidance.
- Add coverage for artifact lifecycle events beyond create where Slack Export
  already owns the mutation: rename and delete are the obvious next candidates.
- Consider a guest artifact open/read event if it can be emitted without
  exposing guest secrets or private corpus text.
- Keep `eventFollow: false` until there is a real follow/SSE/streaming route.

Acceptance target:

- Receipts Live View can explain whether Slack is current, empty, filtered to
  no matches, degraded, or behind without scraping logs.
- Event tests cover filtering by tenant/account, event type, privacy, cursor,
  and limit.

### H4. Keep guest-facing identity child-owned

Receipts should render human labels and emoji, but Slack Export must continue
to own Slack identity resolution and raw provenance preservation.

Requested improvements:

- Ensure search results, context-window rows, selected-result artifacts, and
  event payloads all expose human-readable channel/user labels where policy
  allows.
- Preserve Slack IDs, timestamps, permalinks, raw mrkdwn, and rendering metadata
  under `native_ids`, `source_refs`, `raw_text`, `text_rendering`, or
  equivalent audit fields.
- Add fixture coverage for unresolved, redacted, bot-authored, and normal
  human-authored messages.
- Render Slack emoji aliases into the same display-text lane Receipts consumes,
  while preserving the native text for audit/debugging.

Acceptance target:

- A Receipts result card or evidence inspector never has to show a Slack UUID as
  the primary sender/channel label when Slack Export knows a safe display label.
- Receipts never has to infer Slack identity from raw IDs.

### H5. Provide a narrow tenant-maintenance API for the Receipts settings page

Receipts is the parent frontend, so Slack Export should not rebuild the final
shared operator console. It should expose stable child-owned maintenance
surfaces that Receipts can place on a dedicated Slack settings page.

Requested improvements:

- Keep tenant credential status, activation, live-sync, backfill, retirement,
  and health actions available through protected API routes with redacted
  credential state.
- Make the service profile or a tenant capability endpoint identify which
  actions are available, disabled, dangerous, or require typed confirmation.
- Keep mutation semantics child-owned and same-origin/session protected.
- Avoid making Receipts scrape the Python-rendered `/settings/tenants` page or
  the React `/operator` preview for action availability.

Acceptance target:

- Receipts can build compact Slack API/settings pages using JSON APIs and
  profile/capability data, without duplicating Slack-specific guardrails.

### H6. Keep Slack Export as the reference child, not the parent UI

Slack Export's React/operator work remains useful as a child-service proving
ground, but Receipts is now where the shared search workbench, report creation,
bulk actions, guest links, evidence inspector, and live view should converge.

Boundary:

- Do not move Slack sync, database, tenant setup, projection, or search logic
  into Receipts.
- Do not make Slack Export's browser UI the shared cross-service frontend.
- Do not make guest grants unlock search, artifact listing, creation, rename,
  deletion, runtime reports, tenant actions, or workspace management.
- Do not require Receipts to parse Slack-native identifiers to page evidence,
  render labels, or infer permissions.

## Recommended Priority

1. H1 compatibility smoke gate.
2. H2 service-profile contract tests.
3. H4 identity/display fixture coverage, including emoji rendering.
4. H3 event readiness/lifecycle expansion.
5. H5 tenant-maintenance capability surface.
6. H6 boundary review whenever frontend/operator work resumes.

## Handoff Back To Receipts

When Slack Export completes any item above, leave a concise note for Receipts
that includes:

- commit hash
- changed API/profile fields or artifact fields
- validation command and result
- any remaining parent-side adaptation needed in Receipts
