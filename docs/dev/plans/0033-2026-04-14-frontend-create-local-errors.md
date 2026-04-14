# Frontend Create Local Errors

State: CLOSED
Roadmap: P02
Opened: 2026-04-14

## Scope

Add form-local error feedback for runtime-report and export creation failures.

- keep the existing create API contracts unchanged
- keep the page-level feedback banner as secondary context
- scope local error handling to the two browser create forms only

## Current State

- `/runtime/reports` create failures now render into a local error slot inside the create panel
- `/exports` create failures now render into a local error slot inside the create panel
- successful creates clear the local error slot before showing the existing success banner
- page-level error feedback remains in place for broader context

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - field-level validation hints before create submission
  - per-input error targeting instead of form-level error blocks
  - success-state placement inside the create panels

## Non-Goals

- changing report/export create payloads
- changing inline row rename/delete error behavior
- introducing a frontend framework or client-side state library

## Acceptance Criteria

- runtime-report create failures render in the report create panel
- export create failures render in the export create panel
- successful creates clear the form-local error state
- targeted API/browser tests lock the served create-local error markers

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
