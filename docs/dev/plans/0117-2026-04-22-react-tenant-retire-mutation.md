# 0117 | React Tenant Retire Mutation

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench now supports credential installation, activation,
initial sync, and live-sync start/restart/stop. Tenant retirement still points
operators back to the production settings page.

The existing protected API requires exact tenant-name confirmation and blocks
browser retirement for protected tenants such as `default` and `soylei`.

## Scope

- Expose `Retire tenant` as a danger action for non-protected tenants.
- Require typed tenant-name confirmation before posting retirement.
- Preserve the existing optional `delete_db` choice.
- POST the existing `POST /v1/tenants/<name>/retire` endpoint with
  `confirm`, `delete_db`, and `stop_live_units`.
- Reuse keyed busy, success, error, and refresh behavior through
  `runTrackedMutation`.

## Non-Goals

- Do not bypass backend protected-tenant checks.
- Do not change backend config backup, DB deletion, or live-unit stop behavior.
- Do not add scaffold creation or maintenance backfill.
- Do not introduce global dialog routing.

## Acceptance Criteria

- `Retire tenant` is not shown for protected tenants.
- Clicking it opens a danger confirmation that requires the tenant name.
- The optional mirrored-DB deletion choice is explicit and unchecked by
  default.
- Confirming posts the existing retire payload and refreshes tenant status.
- Frontend typecheck and build pass.

## Definition Of Done

- `TenantWorkbench` owns the Slack-specific retire payload and protected-name
  hiding rule.
- `ConfirmDialog` remains provider-neutral.
- `ROADMAP.md`, `RUNBOOK.md`, and frontend contract docs are updated.
- The slice is committed independently.
