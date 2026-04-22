# 0118 | React Maintenance Backfill Mutation

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench now covers credential installation, activation,
initial sync, live-sync start/restart/stop, and guarded retirement. The
production tenant settings page still exposes a maintenance backfill button for
enabled synced tenants that are not already in the initial-sync state.

## Scope

- Expose a bounded `Run bounded backfill` maintenance action for enabled,
  DB-synced tenants when they are not already in initial-sync or syncing state.
- POST the existing `POST /v1/tenants/<name>/backfill` endpoint with the same
  bounded user-auth payload as the current React initial-sync path.
- Reuse keyed busy, success, error, and refresh behavior through
  `runTrackedMutation`.
- Keep the Slack-specific backfill label and payload in `TenantWorkbench`.

## Non-Goals

- Do not add custom backfill controls for auth mode, channel limit, or files.
- Do not change backend backfill behavior.
- Do not add streaming progress.
- Do not extract shared mutation routing.

## Acceptance Criteria

- `Run bounded backfill` appears as a maintenance action only for eligible
  tenants.
- Initial-sync tenants still show `Run initial sync` as the primary action.
- Submitting the action signals status immediately and refreshes afterward.
- Frontend typecheck and build pass.

## Definition Of Done

- `TenantWorkbench` owns the Slack-specific maintenance backfill eligibility.
- Shared primitives remain provider-neutral.
- `ROADMAP.md`, `RUNBOOK.md`, and frontend contract docs are updated.
- The slice is committed independently.
