# 0111 | React Restart Live Sync Mutation

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench has enabled `Run initial sync` and `Start live sync`
as narrow mutation paths. `Restart live sync` remains a recovery action, not a
general maintenance action, and should only appear when tenant status indicates
degradation while live units are still active.

This slice enables only the restart recovery path. `Stop live sync` remains
disabled until the UI has an explicit confirmation pattern.

## Scope

- Wire `Restart live sync` to the existing `POST /v1/tenants/<name>/live`
  endpoint with `{ action: "restart" }`.
- Enable restart only when sync health is warning and at least one live unit is
  active.
- Reuse per-tenant mutation feedback for busy, success, and error states.
- Refresh tenant status after the command returns.
- Keep stop, activation, credentials, retire, and maintenance backfill disabled.

## Non-Goals

- Do not wire stop.
- Do not add confirmation dialogs.
- Do not change backend live-unit behavior.
- Do not extract a shared package yet.

## Acceptance Criteria

- `Restart live sync` is enabled only for degraded active-unit status.
- Clicking it signals busy state immediately.
- Success and error paths render local feedback and then refresh tenant status.
- Existing frontend validation and browser smoke pass.

## Definition Of Done

- `TenantWorkbench` owns the Slack-specific live-restart payload and refresh.
- `ActionButtonGroup` remains provider-neutral.
- `ROADMAP.md`, `RUNBOOK.md`, and frontend contract docs are updated.
- The slice is committed independently.
