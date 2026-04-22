# 0110 | React Start Live Sync Mutation

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench has one enabled mutation: `Run initial sync`. Other
tenant controls remain disabled while their contracts are migrated deliberately.

This slice enables only `Start live sync` for tenants whose backend status
explicitly reports `next_action: start_live_sync`.

## Scope

- Wire `Start live sync` to the existing `POST /v1/tenants/<name>/live`
  endpoint with `{ action: "start" }`.
- Reuse the existing per-tenant mutation feedback for busy, success, and error
  states.
- Refresh tenant status after the command returns.
- Keep `Restart live sync`, `Stop live sync`, activation, credentials, retire,
  and maintenance backfill disabled.

## Non-Goals

- Do not wire restart or stop.
- Do not add confirmation dialogs.
- Do not change backend live-unit behavior.
- Do not extract a shared package yet.

## Acceptance Criteria

- `Start live sync` is enabled only for explicit `start_live_sync` next-action
  status.
- Clicking it signals busy state immediately.
- Success and error paths render local feedback and then refresh tenant status.
- Existing frontend validation and browser smoke pass.

## Definition Of Done

- `TenantWorkbench` owns the Slack-specific live-start payload and refresh.
- `ActionButtonGroup` remains provider-neutral.
- `ROADMAP.md`, `RUNBOOK.md`, and frontend contract docs are updated.
- The slice is committed independently.
