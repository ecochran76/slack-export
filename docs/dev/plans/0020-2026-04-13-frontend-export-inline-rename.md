# Frontend Export Inline Rename

State: CLOSED
Roadmap: P02
Opened: 2026-04-13

## Scope

Remove the last prompt-driven control from the browser export manager.

- replace export rename prompt dialogs with inline row editing on `/exports`
- keep the implementation thin over the existing export rename API
- keep the rest of the export manager contract unchanged

## Current State

- `/exports` now supports inline rename controls per export row
- rename save/cancel happens in the page instead of through `window.prompt()`
- delete remains a bounded confirmation flow and create remains unchanged

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - inline export rename success state without page reload
  - richer export creation presets
  - export list sorting or filtering beyond the current table

## Non-Goals

- changing export create semantics
- changing export delete semantics
- rewriting the export manager as a SPA

## Acceptance Criteria

- export rename no longer depends on prompt dialogs
- each export row can be renamed inline
- the page still uses the existing export rename API contract

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
