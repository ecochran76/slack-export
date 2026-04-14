# Frontend Busy Labels

State: CLOSED
Roadmap: P02
Opened: 2026-04-14

## Scope

Add explicit inline progress text to the existing browser-manager busy states so disabled controls also communicate what action is happening.

- keep the existing report/export create and inline rename/delete API contracts unchanged
- reuse the shared inline-manager helper instead of introducing a new browser state model
- limit the UI copy changes to temporary in-flight labels such as `creating…`, `saving…`, and `deleting…`

## Current State

- `/runtime/reports` and `/exports` now show `creating…` on the create button while create requests are in flight
- inline rename save buttons now show `saving…` while rename requests are in flight
- inline delete buttons now show `deleting…` while delete requests are in flight
- the original control labels are restored after success or failure

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - visual spinners or progress indicators beyond text labels
  - richer per-row status presentation for longer-running export creation
  - extracting the browser helper JS out of the inline HTML renderer

## Non-Goals

- changing any create, rename, or delete payloads
- adding a frontend framework or build pipeline
- changing auth, CSRF, or browser-session behavior

## Acceptance Criteria

- create buttons on `/runtime/reports` and `/exports` visibly change to `creating…` while create is in flight
- inline save buttons visibly change to `saving…` while rename is in flight
- inline delete buttons visibly change to `deleting…` while delete is in flight
- targeted API/browser tests lock the served busy-label markers

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
