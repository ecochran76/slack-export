# Frontend Export Inline Mutation State

State: CLOSED
Roadmap: P02
Opened: 2026-04-13

## Scope

Remove full-page reloads from successful export rename and delete actions.

- keep the existing export CRUD API routes
- update the `/exports` table inline on successful rename and delete
- keep export creation unchanged in this slice

## Current State

- successful export rename now updates the affected row in place
- successful export delete now removes the affected row in place
- successful rename/delete now surface inline success feedback without reloading the page

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - inline export creation without reload
  - shared browser mutation helpers across report/export managers
  - empty-state row insertion after deleting the last export

## Non-Goals

- changing export create semantics
- changing API payloads
- a broader browser framework refactor

## Acceptance Criteria

- export rename does not reload the page on success
- export delete does not reload the page on success
- the table reflects the mutation result immediately in the browser

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
