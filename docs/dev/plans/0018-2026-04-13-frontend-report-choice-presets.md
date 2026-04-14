# Frontend Report Choice Presets

State: CLOSED
Roadmap: P02
Opened: 2026-04-13

## Scope

Replace the weakest part of the browser runtime-report manager: prompt-driven rename and raw base-URL entry.

- expose configured runtime-report base URL choices in the browser
- replace prompt-based rename with inline row editing
- keep the page thin over the existing runtime-report CRUD API

## Current State

- `/runtime/reports` now offers configured base-URL choices for report creation instead of a raw base-URL text field
- the page now offers guided report-name presets plus a timestamped default
- runtime-report rename now happens inline on the selected row instead of through `window.prompt()`

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - richer report naming conventions by audience or time-of-day
  - browser-side sort/filter for large runtime-report inventories
  - broader browser management polish beyond the current bounded report manager

## Non-Goals

- a SPA or client framework rewrite
- report editing beyond create, rename, and delete
- changing the existing runtime-report storage model

## Acceptance Criteria

- report creation uses configured base-URL choices instead of raw origin entry
- report rename no longer depends on browser prompt dialogs
- the runtime-report manager stays thin over the existing shared API routes

## Validation

- `python -m py_compile slack_mirror/service/app.py slack_mirror/service/api.py tests/test_app_service.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_app_service tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
