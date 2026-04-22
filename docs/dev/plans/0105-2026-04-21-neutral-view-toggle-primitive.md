# 0105 | Neutral View Toggle Primitive

State: CLOSED

Roadmap: P09

## Current State

The React `/operator` tenant workbench has a local `Cards` / `Table` density
switch. Status and table rendering have already moved into local neutral
primitives, but the view switch remains tenant-specific markup.

## Scope

- Add a small provider-neutral `ViewToggle` primitive.
- Keep tenant-specific view-mode names and behavior inside the tenant
  workbench.
- Preserve the current card/table default and interaction behavior.
- Document the primitive as local and convergence-oriented, not a shared
  package extraction.

## Non-Goals

- No persisted user preference.
- No route/query-param synchronization.
- No keyboard roving-tabindex complexity beyond native buttons.
- No mutation controls.
- No shared package extraction.

## Acceptance Criteria

- Tenant card/table switching renders through `ViewToggle`.
- `ViewToggle` accepts generic string-valued options.
- The operator preview still defaults to Cards and switches to Table.
- Browser smoke confirms card and table modes still render without page-level
  horizontal overflow.

## Definition Of Done

- Frontend typecheck and production build pass.
- Planning audit passes.
- Browser smoke confirms the served `/operator` route still switches views.

## Completion Notes

- Added `frontend/src/components/ViewToggle.tsx`.
- Replaced the tenant-local card/table button markup with `ViewToggle`.
- Documented the primitive in the frontend contract notes and roadmap.
