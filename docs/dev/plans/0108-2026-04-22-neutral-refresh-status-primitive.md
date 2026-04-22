# 0108 | Neutral Refresh Status Primitive

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench already polls `/v1/tenants` on a fixed interval, but
the UI did not show when the status was last refreshed or provide an explicit
manual refresh affordance. That makes status-derived action affordances harder
to trust before React tenant mutations are enabled.

This slice adds a provider-neutral refresh-status primitive and keeps API
fetching inside the tenant adapter.

## Scope

- Add a reusable `RefreshStatus` component.
- Render last-updated text, auto-refresh interval text, loading/error tone, and
  a manual refresh button.
- Wire the tenant workbench to track last successful refresh and manual refresh
  state.
- Preserve the existing read-only tenant status adapter and polling endpoint.

## Non-Goals

- Do not add streaming status.
- Do not wire tenant mutations.
- Do not persist refresh settings.
- Do not extract a shared package yet.

## Acceptance Criteria

- The primitive is provider-neutral and does not import tenant types.
- The tenant workbench displays freshness information after the first successful
  status poll.
- Manual refresh triggers a fresh `/v1/tenants` request and updates the visible
  last-updated label.
- Existing frontend validation and browser smoke pass.

## Definition Of Done

- `frontend/src/components/RefreshStatus.tsx` exists and is used by
  `TenantWorkbench`.
- Frontend contract docs describe the primitive and extraction gate.
- `ROADMAP.md` and `RUNBOOK.md` are updated.
- The slice is committed independently.
