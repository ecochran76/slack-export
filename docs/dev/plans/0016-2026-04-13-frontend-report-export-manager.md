# Frontend Report And Export Manager

State: CLOSED
Roadmap: P02
Opened: 2026-04-13

## Scope

Turn the existing report/export CRUD APIs into usable browser surfaces.

- upgrade `/runtime/reports` from a read-only index into a report manager
- add a browser export manager at `/exports`
- keep the implementation thin over the existing API/service lifecycle methods

## Current State

- the browser now has bounded management surfaces over the shipped report/export CRUD APIs
- `/runtime/reports` now supports:
  - create runtime report
  - rename runtime report
  - delete runtime report
- `/exports` now exists as a browser export manager and supports:
  - create channel-day export
  - rename export bundle
  - delete export bundle
- the landing page now links to `/exports` as the primary browser entrypoint for export management

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - richer validation and inline field guidance
  - browser-side pagination/filtering for large report/export sets
  - additional browser management pages beyond reports and exports

## Non-Goals

- replacing the underlying CRUD APIs with browser-only logic
- supporting arbitrary export kinds beyond channel-day
- building a large SPA or design-system migration

## Acceptance Criteria

- authenticated users can create, rename, and delete runtime reports from `/runtime/reports`
- authenticated users can create, rename, and delete channel-day exports from `/exports`
- the landing page points to the browser management surfaces instead of only the raw manifest APIs

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
