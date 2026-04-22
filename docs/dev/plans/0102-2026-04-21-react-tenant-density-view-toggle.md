# 0102 | React Tenant Density View Toggle

State: CLOSED

Roadmap: P09

## Current State

The React `/operator` preview renders full-width tenant cards backed by the
existing `/v1/tenants` API. The cards now keep critical status visible and move
secondary diagnostics behind disclosures, but the page still needs a compact
operator view so dense tenant fleets can be scanned before action controls
migrate into React.

## Scope

- Keep the tenant workbench read-only.
- Add an in-page `Cards` / `Table` density toggle.
- Preserve the card view as the default.
- Add a compact table view using the same tenant status, DB stats, backfill,
  live-sync, health, and semantic-readiness data.
- Keep table diagnostics accessible through per-row disclosure controls.
- Validate the served `/operator` route with `agent-browser`.

## Non-Goals

- No tenant mutations in React.
- No persisted user preference yet.
- No new API fields or backend behavior.
- No shared UI package extraction.

## Acceptance Criteria

- Operators can switch between card and compact table views.
- The compact table exposes tenant identity, runtime readiness, DB counts,
  backfill, live-sync, health, and semantic readiness.
- Table diagnostics can be expanded without leaving the page.
- Mobile layout avoids page-level horizontal overflow.
- Existing card behavior remains intact.

## Definition Of Done

- Frontend typecheck and production build pass.
- Planning audit passes.
- `agent-browser` confirms the toggle, table view, cards view, tenants, and
  overflow behavior against the live preview route.

## Completion Notes

- Added a local React density view state with `Cards` as the default.
- Added a compact tenant table with per-row diagnostic disclosures.
- Added responsive table scrolling inside the workbench rather than allowing
  page-level overflow.
