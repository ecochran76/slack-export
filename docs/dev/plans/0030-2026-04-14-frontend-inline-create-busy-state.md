# Frontend Inline Create Busy State

State: CLOSED
Roadmap: P02
Opened: 2026-04-14

## Scope

Prevent duplicate create submissions in the browser managers by disabling create controls while report or export creation is in flight.

- keep the existing create API contracts unchanged
- keep the current inline create UX unchanged apart from temporary disabled controls
- apply the create busy-state behavior independently to `/runtime/reports` and `/exports`

## Current State

- `/runtime/reports` now disables its create controls while report creation is in flight
- `/exports` now disables its create controls while export creation is in flight
- successful and failed create responses both clear the temporary disabled state

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - inline spinners or progress messaging for long-running create flows
  - preserving more nuanced enabled/disabled channel selector state after export create completes
  - broader browser component extraction

## Non-Goals

- changing report/export create payloads
- changing row-level rename/delete busy-state behavior
- introducing a frontend framework or asset pipeline

## Acceptance Criteria

- report create cannot be double-fired while a create request is in flight
- export create cannot be double-fired while a create request is in flight
- targeted API/browser tests lock the served create busy-state markers

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
