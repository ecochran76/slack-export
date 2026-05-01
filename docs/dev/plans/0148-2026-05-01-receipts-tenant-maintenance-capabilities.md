# 0148 | Receipts tenant maintenance capabilities

State: CLOSED

Roadmap: P12

## Context

Receipts homework H5 asks Slack Export to keep tenant credential status,
activation, live sync, backfill, retirement, and health management child-owned
while still giving a shared Receipts settings page enough machine-readable
metadata to render controls without scraping `/settings/tenants` or `/operator`.

## Current State

Shipped baseline:

- `/v1/tenants` already exposes redacted tenant status, DB stats, backfill
  state, live unit state, health, and `next_action`.
- Protected API routes already exist for scaffold creation, credential install,
  activation, live sync, bounded backfill, retirement, and manifest retrieval.
- Same-origin write protection already covers tenant mutations.

Shipped in this slice:

- `/v1/service-profile` now advertises a `tenantMaintenance` capability object
  with Slack-owned route templates, action identifiers, danger flags, and
  confirmation requirements.
- `/v1/tenants` now includes per-tenant `maintenance_actions` with concrete
  action paths, enabled/disabled state, disabled reasons, danger flags, typed
  confirmation values, and default body templates.
- `GET /v1/tenants/{tenant}` now returns the same redacted single-tenant status
  shape for settings pages that need a focused refresh.

Remaining work:

- Keep mutation execution inside Slack-owned routes; Receipts should only proxy
  same-origin child-session calls.
- Revisit the action labels after Receipts has a concrete settings layout, but
  do not make Receipts infer Slack lifecycle state from display strings.

## Scope

- Add redacted action metadata in `slack_mirror.service.tenant_onboarding`.
- Add tenant-maintenance discovery metadata to `/v1/service-profile`.
- Add a focused single-tenant status route.
- Update contract tests, docs, roadmap, and runbook.

## Non-Goals

- Do not move tenant mutation logic into Receipts.
- Do not expose raw Slack tokens, signing secrets, or dotenv values.
- Do not add a new frontend settings implementation in this slice.

## Acceptance

- Service profile identifies tenant-maintenance route templates and action
  semantics.
- Tenant status identifies which actions are enabled, disabled, dangerous, or
  confirmation-protected.
- Tenant actions remain protected by child session and same-origin write rules.
- Tests prove the contract without depending on live private tenant state.

## Validation

Passed:

- `./.venv/bin/python -m py_compile slack_mirror/service/api.py slack_mirror/service/tenant_onboarding.py tests/test_api_server.py tests/test_tenant_onboarding.py`
- `./.venv/bin/python -m unittest tests.test_api_server.ApiServerTests.test_service_profile_receipts_contract_is_stable tests.test_api_server.ApiServerTests.test_tenant_status_and_onboard_api tests.test_tenant_onboarding.TenantOnboardingTests.test_tenant_status_reports_missing_credentials_without_secret_values tests.test_tenant_onboarding.TenantOnboardingTests.test_tenant_status_prefers_run_initial_sync_when_live_units_are_active_without_reconcile_state -v`
- `./.venv/bin/python scripts/smoke_receipts_compatibility.py --json`
- `/home/ecochran76/.local/share/slack-mirror/venv/bin/python -m pip install -e /home/ecochran76/workspace.local/slack-export`
- `systemctl --user restart slack-mirror-api.service && sleep 1 && curl -sS http://127.0.0.1:8787/v1/health`
- `./.venv/bin/python scripts/smoke_receipts_compatibility.py --base-url http://127.0.0.1:8787 --query "website service" --json`
- `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git diff --check`

## Next Recommended Action

Complete H6 with a concise boundary review and one consolidated Slack-to-Receipts
handoff so the Receipts agent can consume the finished H1-H5 contract work.
