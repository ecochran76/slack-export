# Frontend Export Inline Create

State: CLOSED
Roadmap: P02
Opened: 2026-04-14

## Scope

Remove the remaining full-page reload from successful export creation on `/exports`.

- keep the existing export CRUD API routes
- insert the created export row inline on success
- keep report creation unchanged in this slice

## Current State

- successful export creation now inserts the new row inline at the top of the table
- create success now surfaces inline feedback without reloading the page
- export rename/delete inline behavior remains intact

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - shared browser mutation helpers across report/export managers
  - empty-state row insertion after deleting the final export
  - guided post-create navigation or reveal behavior

## Non-Goals

- changing export create API payloads
- changing report creation behavior
- a broader browser framework refactor

## Acceptance Criteria

- export create does not reload the page on success
- the new export row appears immediately in the browser
- export rename/delete continue to work inline after insertion

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
