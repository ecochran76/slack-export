# 0152 | Receipts Tenant Mutation Handshake

State: CLOSED

Roadmap: P12

## Context

Receipts left a Slack tenant executable-flow design review asking Slack Export
to confirm the child-owned handshake before Receipts enables Slack tenant
maintenance dispatch.

Relevant Receipts notes:

- `../receipts/docs/dev/notes/0023-2026-05-01-slack-tenant-mutation-promotion-checklist.md`
- `../receipts/docs/dev/notes/0024-2026-05-01-slack-tenant-executable-flow-design-review.md`

## Current State

- Slack Export already exposes tenant maintenance route and action metadata
  through `/v1/service-profile`, `/v1/tenants`, and `/v1/tenants/{tenant}`.
- Receipts already renders and prepares those actions, but intentionally keeps
  dispatch disabled.
- The missing gap was an explicit Slack-owned contract for session/CSRF
  metadata, executable source of truth, mutation response shape, idempotency
  behavior, and post-action refresh guidance.

## Shipped

- `/v1/service-profile` now exposes `tenantMaintenance.executionContract`.
- Profile-level tenant action descriptors are explicitly non-executable
  templates.
- Concrete per-tenant `maintenance_actions` now include:
  - `executable_source`
  - `transport_mode`
  - `response_shape`
  - `idempotency`
  - `refresh_recommendation`
- `/auth/session` now includes session `state`, tenant-maintenance permission
  booleans, and tenant-maintenance CSRF metadata.
- Tenant mutation responses now include a safe `operation` object with schema
  `tenant_maintenance_operation_v1` plus a top-level `refresh`
  recommendation.
- `docs/API_MCP_CONTRACT.md` now records the Receipts-facing handshake and stop
  rules.

## Decisions

- Receipts should execute only concrete per-tenant `maintenance_actions`, not
  profile-level action templates.
- Slack tenant writes require child-session cookies plus same-origin
  `Origin`/`Referer`; no CSRF token, nonce, or custom header is required.
- Expired/revoked child sessions currently normalize to unauthenticated; there
  is no role-based insufficient-permission state yet.
- Child-owned idempotency keys are not supported for tenant maintenance writes;
  Receipts must suppress duplicate clicks, keep one dispatch in flight, and
  refresh status before retrying.

## Validation

- `./.venv/bin/python -m py_compile slack_mirror/service/api.py slack_mirror/service/tenant_onboarding.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server.ApiServerTests.test_service_profile_receipts_contract_is_stable tests.test_api_server.ApiServerTests.test_tenant_status_and_onboard_api tests.test_api_server.ApiServerTests.test_frontend_auth_register_login_settings_and_session_revoke -v`
- `./.venv/bin/python scripts/smoke_receipts_compatibility.py --json`
- `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git diff --check`
