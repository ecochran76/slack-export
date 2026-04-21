# 0100 | React Tenant Workbench Browser QA

State: CLOSED

Roadmap: P09

## Current State

- `0099` made `/operator` fetch `/v1/tenants` and render a read-only React tenant-status workbench.
- Browser QA with `agent-browser` confirmed that the live worktree API server serves `/operator` and that tenant status loads for `default`, `soylei`, and `pcg`.
- The first browser screenshot found two polish issues:
  - the app shell topbar still said `Selected Result Workbench`
  - long status chips could collide with status-panel labels, especially `monitor_live_validation`
- The React tenant workbench now has a route-appropriate shell title and safer wrapping/formatting for long status labels.

## Scope

- Use `agent-browser` against the worktree-served `/operator` preview route.
- Fix browser-observed title and status-chip layout issues.
- Keep the adapter read-only and keep tenant mutations on `/settings/tenants`.
- Update roadmap and runbook wiring.

## Non-Goals

- Do not add React-side tenant mutation controls.
- Do not replace the Python-rendered tenant settings page.
- Do not change `/v1/tenants` payload semantics.
- Do not redesign the full shell/navigation model in this slice.

## Acceptance Criteria

- `/operator` shell title matches the tenant workbench.
- Long status labels are human-readable and do not collide with panel headings.
- `agent-browser` verifies that tenants render from `/v1/tenants`.
- Frontend build/typecheck and planning checks pass.

## Definition Of Done

- `npm run typecheck` passes from `frontend/`.
- `npm run build` passes from `frontend/`.
- Browser QA captures `/operator` after fixes.
- `git diff --check` passes.
- Planning contract audit passes.

## Completion Notes

- Added configurable `OperatorShell` title/eyebrow props.
- Updated `/operator` to show `Tenant Status Workbench` in the global shell.
- Added status-label formatting and wrapping to prevent long badges from colliding.
