# 0116 | React Credential Install Form

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench can run initial sync, live-sync start/restart/stop,
and the one-click activation sequence. A tenant with missing Slack credentials
still points operators back to the production settings page.

The existing protected API already supports credential installation without
echoing secret values in the response.

## Scope

- Enable `Install credentials` only when a tenant is missing required
  credentials.
- Show a compact per-tenant credential form with password inputs.
- Submit only non-empty credential fields to the existing
  `POST /v1/tenants/<name>/credentials` endpoint.
- Reuse keyed busy, success, error, and refresh behavior through
  `runTrackedMutation`.
- Keep Slack-specific credential names and payload mapping in `TenantWorkbench`.

## Non-Goals

- Do not add tenant scaffold creation, retirement, or maintenance backfill.
- Do not store credential values in React state.
- Do not echo secret values in feedback or docs.
- Do not change backend dotenv, backup, or redaction behavior.

## Acceptance Criteria

- `Install credentials` opens a tenant-local form when credentials are missing.
- Submitting the form signals status immediately.
- Returned feedback reports counts/readiness without secret values.
- Tenant status refreshes after credential installation settles.
- Frontend typecheck and build pass.

## Definition Of Done

- `TenantWorkbench` owns Slack-specific credential fields and payloads.
- Shared primitives remain provider-neutral.
- `ROADMAP.md`, `RUNBOOK.md`, and frontend contract docs are updated.
- The slice is committed independently.
