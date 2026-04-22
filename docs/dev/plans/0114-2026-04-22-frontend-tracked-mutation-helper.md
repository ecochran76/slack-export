# 0114 | Frontend Tracked Mutation Helper

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench now has four narrow mutation paths: initial sync,
start live sync, restart live sync, and stop live sync. Each path repeats the
same busy, success, error, and refresh-state bookkeeping.

This duplication is still local, but adding activation, credential, retire, or
maintenance backfill without a small helper would make the workbench harder to
audit and less reusable for the later `../imcli` and `../ragmail` operator
console convergence path.

## Scope

- Add a provider-neutral frontend helper for keyed mutation state.
- Keep Slack-specific API routes, payloads, and operator-facing labels inside
  the tenant workbench.
- Refactor initial-sync and live-sync mutations to use the helper.
- Preserve the existing UI behavior and post-command tenant refresh behavior.
- Document the helper as a local proving step, not a shared-package extraction.

## Non-Goals

- Do not wire activation, credentials, retire, or maintenance backfill.
- Do not add optimistic updates.
- Do not introduce global mutation routing or app-wide stores.
- Do not extract a sibling shared package yet.

## Acceptance Criteria

- The mutation helper has no Slack-specific tenant/workspace terminology.
- Existing tenant mutation actions still show immediate busy feedback.
- Success and error feedback still remains keyed by tenant name.
- Tenant status still refreshes after mutation completion or failure.
- Frontend typecheck and build pass.

## Definition Of Done

- `TenantWorkbench` delegates repeated mutation-state mechanics to the helper.
- `ROADMAP.md`, `RUNBOOK.md`, and frontend contract docs are updated.
- The slice is committed independently.
