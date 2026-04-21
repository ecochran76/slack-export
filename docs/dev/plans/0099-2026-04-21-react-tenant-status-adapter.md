# 0099 | React Tenant Status Adapter

State: CLOSED

Roadmap: P09

## Current State

- `0098` serves the built React operator preview at `/operator` behind the existing frontend-auth guard.
- The production `/settings/tenants` Python-rendered page remains the mutation surface for scaffold, credential install, activation, live sync, backfill, and retirement.
- The existing `/v1/tenants` API already returns tenant status, credential readiness, DB stats, live unit states, backfill status, health, next action, and semantic readiness.
- The React preview now reads `/v1/tenants` and renders a read-only tenant-status workbench using the new shell and theme primitives.

## Scope

- Add a small frontend API helper for same-origin JSON reads.
- Add Slack-local tenant status types and a read-only tenant-status adapter.
- Replace the static selected-result preview as the default `/operator` screen with a tenant-status workbench.
- Render dense tenant rows with status badges, metric strips, DB stats, backfill status, live-sync status, health, semantic readiness, and a link back to `/settings/tenants` for mutations.
- Keep the fetch poll-first and bounded, with loading, error, and empty states.
- Update roadmap and runbook wiring.

## Non-Goals

- Do not add tenant mutation controls to the React app in this slice.
- Do not replace `/settings/tenants`.
- Do not add a new backend API endpoint.
- Do not extract shared packages or introduce frontend routing yet.
- Do not change tenant API, MCP, CLI, auth, or live-unit semantics.

## Acceptance Criteria

- `/operator` frontend code fetches `/v1/tenants` with same-origin credentials.
- Tenant rows show DB stats, backfill status, live status, health, next action, and semantic readiness in a dense read-only layout.
- Mutating tenant work remains linked to `/settings/tenants`.
- Frontend typecheck/build pass.
- Planning audit and diff checks pass.

## Definition Of Done

- `npm run typecheck` passes from `frontend/`.
- `npm run build` passes from `frontend/`.
- Relevant API preview-route validation still passes.
- `git diff --check` passes.
- Planning contract audit passes.

## Completion Notes

- Added `frontend/src/lib/api.ts`.
- Added tenant status types and `TenantWorkbench`.
- Changed the default React app screen to the read-only tenant workbench.
- Kept selected-result contracts and placeholder component available for later search/report slices.
