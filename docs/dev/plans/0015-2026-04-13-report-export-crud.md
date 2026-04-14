# Report And Export CRUD

State: CLOSED
Roadmap: P02
Opened: 2026-04-13

## Scope

Add bounded create/read/update/delete operations for managed runtime reports and managed export bundles through the shared service and local API.

- runtime report create, read, rename, delete
- channel-day export create, read, rename, delete
- shared service ownership for the lifecycle methods
- API write routes for the same bounded operations

## Current State

- runtime reports are already readable through `/v1/runtime/reports*` and `/runtime/reports*`
- managed export bundles are already readable through `/v1/exports*` and `/exports/<export-id>`
- report storage ownership already lives in `slack_mirror.service.runtime_report`
- export storage ownership already lives in `slack_mirror.exports`
- this slice now ships:
  - runtime report rename/delete helpers
  - export bundle rename/delete helpers
  - shared app-service lifecycle methods
  - API POST/DELETE routes for runtime report and export CRUD

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - browser CRUD forms
  - MCP write parity
  - additional export kinds beyond channel-day
  - background-job orchestration for export creation

## Non-Goals

- arbitrary export kinds beyond channel-day
- browser CRUD forms
- MCP write parity
- background-job orchestration for export generation

## Acceptance Criteria

- runtime reports support create, read, rename, and delete through shared service and API
- managed channel-day exports support create, read, rename, and delete through shared service and API
- update semantics remain intentionally narrow to rename-only operations
- lifecycle helpers keep report/export manifests coherent after rename or delete

## Validation

- `python -m py_compile slack_mirror/exports.py slack_mirror/service/runtime_report.py slack_mirror/service/app.py slack_mirror/service/api.py tests/test_exports.py tests/test_runtime_report.py tests/test_app_service.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_exports tests.test_runtime_report tests.test_app_service tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
