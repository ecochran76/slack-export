# Frontend Inline Manager Helper Consolidation

State: CLOSED
Roadmap: P02
Opened: 2026-04-14

## Scope

Consolidate the duplicated browser-side rename/delete row-binding logic shared by `/runtime/reports` and `/exports`.

- keep the current browser UI and API behavior unchanged
- factor duplicated inline-mutation event wiring into one shared helper in `api.py`
- keep this slice internal and maintainability-focused

## Current State

- `/runtime/reports` and `/exports` now use one shared browser-side row-action binder for inline rename/delete behavior
- page-specific create, row rendering, and API payload differences remain explicit
- no operator-visible route or payload changes were introduced in this slice

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - broader shared browser component extraction
  - empty-state cleanup after deleting the final row
  - richer client-side create flows

## Non-Goals

- changing runtime-report or export CRUD API behavior
- changing rendered page structure in a user-visible way
- introducing a frontend framework or asset pipeline

## Acceptance Criteria

- the duplicated inline rename/delete binder is consolidated into one shared helper
- `/runtime/reports` and `/exports` keep their current inline behavior
- targeted API/browser tests still pass

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
