# Frontend Export Channel Filter

State: CLOSED
Roadmap: P02
Opened: 2026-04-13

## Scope

Make the browser export manager usable for larger mirrored workspaces.

- add channel filtering on `/exports`
- keep channel selection bounded to valid mirrored choices already loaded from the service
- keep the browser flow thin over the existing export CRUD and workspace/channel-list APIs

## Current State

- `/exports` now includes a browser-side channel filter input
- loaded channel choices are filtered client-side by name, id, class, and recent-activity metadata
- the page surfaces match counts and empty-filter feedback instead of leaving the user in a long undifferentiated select

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - typeahead/autocomplete selection beyond a filtered native select
  - date suggestions beyond latest mirrored day
  - inline export rename controls matching the report manager

## Non-Goals

- server-side channel search APIs
- a SPA or component-library rewrite
- changing the existing managed export contract

## Acceptance Criteria

- `/exports` keeps using only valid mirrored channel choices
- users can filter large channel lists before selecting a channel
- the UI shows useful feedback when a filter returns no matches

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
