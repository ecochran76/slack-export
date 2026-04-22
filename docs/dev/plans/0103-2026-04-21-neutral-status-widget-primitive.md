# 0103 | Neutral Status Widget Primitive

State: CLOSED

Roadmap: P09

## Current State

The React `/operator` preview now has card and compact table views for tenant
status. Status chips and panels are still expressed as ad hoc tenant-workbench
markup, which makes future convergence with `../imcli` and `../ragmail` harder
than necessary.

## Scope

- Add the first provider-neutral status UI primitive.
- Keep Slack-specific API tone and label mapping inside the tenant adapter.
- Replace tenant-local status badge/panel markup with the shared primitive.
- Document the shared-vs-repo-local status boundary.
- Keep all behavior read-only.

## Non-Goals

- No package extraction into a sibling shared repo.
- No new backend API fields.
- No tenant mutation controls.
- No visual redesign beyond preserving the current look through reusable
  components.

## Acceptance Criteria

- Status tone is represented through a neutral frontend contract.
- `StatusBadge` and `StatusPanel` can be reused by later search, report, logs,
  `imcli`, or `ragmail` adapters without Slack-specific naming.
- Tenant-specific status labels remain formatted in the Slack tenant adapter.
- The operator preview still renders tenant cards and table rows correctly.

## Definition Of Done

- Frontend typecheck and production build pass.
- Planning audit passes.
- Browser smoke confirms cards, table mode, and status widgets still render
  against the live preview route.

## Completion Notes

- Added `frontend/src/contracts/status.ts`.
- Added `frontend/src/components/StatusWidget.tsx`.
- Updated the tenant workbench to consume `StatusBadge` and `StatusPanel`.
- Updated frontend contract notes to make the convergence boundary explicit.
