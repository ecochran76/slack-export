# 0104 | Neutral Entity Table Primitive

State: CLOSED

Roadmap: P09

## Current State

The React `/operator` preview has a compact tenant table and neutral status
widgets. The compact table still owns its table shell, header, body, row-key,
and row-header semantics inside the Slack tenant workbench, which limits reuse
for future `../imcli` account/chat views and `../ragmail` mailbox/source views.

## Scope

- Add a small provider-neutral `EntityTable` primitive.
- Keep tenant-specific columns, cell content, and status mapping inside the
  Slack tenant adapter.
- Move table shell, ARIA region, column headers, row keys, row headers, and row
  cell rendering into the reusable component.
- Rename table CSS from tenant-specific selectors to neutral entity-table
  selectors.
- Keep all behavior read-only.

## Non-Goals

- No shared package extraction.
- No sorting, filtering, pagination, selection, or mutation controls.
- No backend API changes.
- No changes to card-mode tenant rendering.

## Acceptance Criteria

- The compact tenant table renders through `EntityTable`.
- The table primitive accepts provider-neutral columns and rows.
- Slack-specific tenant fields remain isolated to `TenantWorkbench`.
- The compact table preserves existing browser behavior and no page-level
  horizontal overflow.

## Definition Of Done

- Frontend typecheck and production build pass.
- Planning audit passes.
- Browser smoke confirms card mode, table mode, tenant rows, and table details
  still render against the live preview route.

## Completion Notes

- Added `frontend/src/components/EntityTable.tsx`.
- Updated tenant table rendering to provide neutral column definitions.
- Renamed table styling to `entity-table` selectors.
- Documented the table primitive as repo-local but convergence-oriented.
