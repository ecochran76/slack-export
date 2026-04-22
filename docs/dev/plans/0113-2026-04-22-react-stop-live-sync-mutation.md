# 0113 | React Stop Live Sync Mutation

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench supports narrow live mutations for initial sync,
start live sync, and restart live sync. `Stop live sync` was intentionally
blocked until a typed confirmation pattern existed.

This slice wires stop through the neutral confirmation dialog.

## Scope

- Expose `Stop live sync` only when at least one live unit is active.
- Require typed tenant-name confirmation before running stop.
- Wire confirmed stop to the existing `POST /v1/tenants/<name>/live` endpoint
  with `{ action: "stop" }`.
- Reuse per-tenant mutation feedback for busy, success, and error states.
- Refresh tenant status after the command returns.

## Non-Goals

- Do not wire activation, credentials, retire, or maintenance backfill.
- Do not change backend live-unit behavior.
- Do not add global dialog routing.
- Do not extract a shared package yet.

## Acceptance Criteria

- `Stop live sync` appears only for tenants with active live-unit evidence.
- Clicking it opens `ConfirmDialog` and requires the tenant name.
- Confirming posts the existing stop payload and then refreshes status.
- Existing frontend validation and browser smoke pass without stopping real
  live units.

## Definition Of Done

- `TenantWorkbench` owns the Slack-specific stop payload and refresh.
- `ConfirmDialog` remains provider-neutral.
- `ROADMAP.md`, `RUNBOOK.md`, and frontend contract docs are updated.
- The slice is committed independently.
