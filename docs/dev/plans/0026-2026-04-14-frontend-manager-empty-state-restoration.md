# Frontend Manager Empty-State Restoration

State: CLOSED
Roadmap: P02
Opened: 2026-04-14

## Scope

Restore explicit empty-state rows on the browser management tables after deleting the final item from `/runtime/reports` or `/exports`.

- keep the existing report/export CRUD API unchanged
- keep the current inline mutation model unchanged
- restore a visible empty-state row instead of leaving an empty table body after the final delete

## Current State

- `/runtime/reports` now restores a `report-empty-row` after deleting the final report row
- `/exports` now restores an `export-empty-row` after deleting the final export row
- successful create flows still remove those empty rows before prepending the created item

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - latest-row promotion cleanup after more complex report mutations
  - broader empty-state styling polish across browser surfaces
  - deeper browser component extraction

## Non-Goals

- changing runtime-report or export CRUD API payloads
- changing filesystem lifecycle semantics for reports or exports
- introducing a frontend framework or asset pipeline

## Acceptance Criteria

- deleting the final runtime report restores an explicit empty-state row
- deleting the final export restores an explicit empty-state row
- successful create flows still remove the empty-state row before inserting the new item
- targeted API/browser tests lock the served HTML/JS markers for the restored empty-state behavior

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
