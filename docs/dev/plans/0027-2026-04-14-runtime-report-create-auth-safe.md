# Runtime Report Create Auth-Safe Snapshoting

State: CLOSED
Roadmap: P02
Opened: 2026-04-14

## Scope

Fix runtime-report creation under browser auth by removing the unauthenticated loopback dependency from the shared runtime-report snapshot path.

- keep the runtime report API contract unchanged
- keep the browser report manager UX unchanged
- build snapshots from shared service payloads instead of HTTP self-calls when invoked through the app service

## Current State

- `create_runtime_report()` now passes shared runtime-status and live-validation payloads directly into snapshot creation
- runtime report snapshot writing still supports HTTP fetch mode for standalone script-style callers
- authenticated browser report creation no longer depends on unauthenticated requests to `/v1/runtime/status` or `/v1/runtime/live-validation`

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - broader live browser CRUD smoke coverage
  - explicit latest-row behavior under more complex report lifecycle changes
  - further consolidation between script-driven and service-driven runtime report generation

## Non-Goals

- changing the runtime report manifest format
- changing `/v1/runtime/reports` request or response payloads
- changing report retention, rename, or delete behavior

## Acceptance Criteria

- authenticated runtime report creation succeeds without depending on unauthenticated loopback API calls
- the shared service layer passes concrete runtime-status and live-validation payloads into snapshot generation
- targeted app-service and API tests cover the auth-safe creation path

## Validation

- `python -m py_compile slack_mirror/service/runtime_report.py slack_mirror/service/app.py tests/test_app_service.py`
- `./.venv/bin/python -m unittest tests.test_app_service tests.test_api_server tests.test_runtime_report -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
