# 0115 | React Activate Tenant Mutation

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench supports narrow initial-sync and live-sync mutations
and now shares keyed mutation-state mechanics through `runTrackedMutation`.
Disabled tenants that are credential-ready and DB-synced still point operators
back to the production settings page for activation.

The production settings page treats activation as a one-click operator action:
enable the tenant, install live units, then start a bounded initial history
sync.

## Scope

- Enable `Activate tenant` in React only when the tenant reports
  `next_action: ready_to_activate`.
- POST the existing `POST /v1/tenants/<name>/activate` endpoint.
- After activation succeeds, POST the existing bounded initial-sync backfill
  payload.
- Reuse keyed busy, success, error, and refresh behavior through
  `runTrackedMutation`.
- Keep Slack-specific activation payloads and labels in `TenantWorkbench`.

## Non-Goals

- Do not add credential installation, tenant scaffold creation, retirement, or
  maintenance backfill.
- Do not change backend activation or live-unit installation behavior.
- Do not add optimistic updates or background streaming.
- Do not extract a shared package.

## Acceptance Criteria

- `Activate tenant` is enabled only for `ready_to_activate` tenants.
- Clicking it signals status immediately.
- A successful activation also starts the bounded initial history sync.
- Success and error feedback remain row-local and keyed by tenant name.
- Tenant status refreshes after the activation sequence settles.

## Definition Of Done

- `TenantWorkbench` owns the Slack-specific activation sequence.
- `ActionButtonGroup` and `runTrackedMutation` remain provider-neutral.
- `ROADMAP.md`, `RUNBOOK.md`, and frontend contract docs are updated.
- The slice is committed independently.
