# Frontend Row-Local Errors

State: CLOSED
Roadmap: P02
Opened: 2026-04-14

## Scope

Add row-local error feedback to the browser report/export managers for inline rename and delete failures.

- keep the existing page-level feedback banners
- keep the existing rename/delete API contracts unchanged
- scope row-local error handling to inline row mutations only

## Current State

- `/runtime/reports` rows now include a hidden row-local error slot that is populated when rename or delete fails
- `/exports` rows now include a hidden row-local error slot that is populated when rename or delete fails
- row-local errors clear when the operator retries, cancels rename, or opens the rename form again
- page-level feedback remains in place as secondary error context

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - row-local success states beyond the existing page-level success banner
  - create-form local error presentation
  - richer validation hints before rename/delete submission

## Non-Goals

- changing report/export create behavior
- replacing the existing page-level feedback banner
- introducing a frontend framework or component library

## Acceptance Criteria

- rename failures show a visible row-local error on `/runtime/reports`
- delete failures show a visible row-local error on `/runtime/reports`
- rename failures show a visible row-local error on `/exports`
- delete failures show a visible row-local error on `/exports`
- targeted API/browser tests lock the served row-local error markers

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
