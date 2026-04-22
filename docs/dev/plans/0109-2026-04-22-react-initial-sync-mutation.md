# 0109 | React Initial Sync Mutation

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench can read tenant status, show freshness, and render
status-derived action affordances. Before this slice, every action remained
disabled and actual tenant mutations still lived only on the production
`/settings/tenants` page.

This slice proves the first narrow React mutation path by enabling only
`Run initial sync` when tenant status reports that initial history sync is the
next action.

## Scope

- Extend `ActionButtonGroup` so callers can provide enabled callbacks.
- Keep all non-initial-sync actions disabled.
- Wire React `Run initial sync` to `POST /v1/tenants/<name>/backfill` with the
  same bounded payload used by the production tenant settings page:
  - `auth_mode: user`
  - `include_messages: true`
  - `include_files: false`
  - `channel_limit: 10`
- Show immediate busy feedback, success/error feedback, and refresh tenant
  status after the command returns.

## Non-Goals

- Do not wire activation, live-sync, credential, retire, or bounded maintenance
  backfill controls.
- Do not add confirmation dialogs.
- Do not change the backend tenant backfill contract.
- Do not extract a shared package yet.

## Acceptance Criteria

- The action primitive remains provider-neutral.
- `Run initial sync` is enabled only for tenants whose status indicates initial
  sync/backfill is needed.
- Clicking `Run initial sync` signals busy state immediately.
- Success and error paths render local feedback and then refresh tenant status.
- Existing frontend validation and browser smoke pass.

## Definition Of Done

- `TenantWorkbench` owns the Slack-specific mutation payload and status refresh.
- `ActionButtonGroup` supports enabled action callbacks without importing
  tenant types.
- `ROADMAP.md`, `RUNBOOK.md`, and frontend contract docs are updated.
- The slice is committed independently.
