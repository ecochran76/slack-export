# 0107 | Neutral Action Button Group Primitive

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench now renders live read-only status, dense cards,
compact tables, status widgets, view toggles, and expandable diagnostics.
Actual tenant mutation workflows still belong to the production
`/settings/tenants` page until React parity is intentionally reached.

This slice adds a reusable action-group primitive and uses it only for
status-derived, disabled recommended actions so operators can see what action
the tenant state implies without triggering partially migrated mutations.

## Scope

- Add a neutral `ActionButtonGroup` primitive for grouped action affordances.
- Support action label, tone, disabled state, and explanatory reason text.
- Derive one recommended tenant action from status in the local tenant
  workbench.
- Show the derived action in card mode and inside compact table diagnostics.
- Keep actual mutations routed to the existing production tenant settings page.

## Non-Goals

- Do not wire React tenant mutations.
- Do not add async action state, optimistic updates, or retry behavior.
- Do not extract a shared package yet.
- Do not replace the production `/settings/tenants` action flow.

## Acceptance Criteria

- The primitive is provider-neutral and does not import tenant types.
- Tenant cards display a status-derived recommended action.
- Tenant table inspect drawers display the same action context without adding
  another wide table column.
- All actions are disabled in this slice and clearly explain where production
  actions still live.
- Existing frontend validation and browser smoke pass.

## Definition Of Done

- `frontend/src/components/ActionButtonGroup.tsx` exists and is used by
  `TenantWorkbench`.
- Frontend contract docs describe the primitive and extraction gate.
- `ROADMAP.md` and `RUNBOOK.md` are updated.
- The slice is committed independently.
