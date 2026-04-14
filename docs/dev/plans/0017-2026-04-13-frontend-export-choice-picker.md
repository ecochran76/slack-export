# Frontend Export Choice Picker

State: CLOSED
Roadmap: P02
Opened: 2026-04-13

## Scope

Replace the weakest part of the browser export manager: raw free-text export creation inputs.

- add a shared API surface for valid mirrored channel choices per workspace
- populate the browser export form from those valid choices
- keep the form thin over the existing export CRUD API

## Current State

- `/v1/workspaces/{workspace}/channels` now returns valid mirrored channel choices, including:
  - `channel_id`
  - `name`
  - `channel_class`
  - `message_count`
  - `latest_message_day`
- `/exports` now uses dependent workspace/channel selectors instead of raw free-text fields
- selecting a channel now surfaces mirrored metadata and defaults the date field to the latest mirrored day for that channel when available

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - richer date suggestions beyond latest mirrored day
  - channel search/autocomplete for large workspaces
  - additional browser creation flows beyond channel-day exports

## Non-Goals

- arbitrary export kinds beyond channel-day
- a full SPA or heavy client framework
- replacing the shared service/API ownership model

## Acceptance Criteria

- the browser export manager only offers valid workspace/channel choices from the current mirror state
- selecting a workspace loads its mirrored channels
- selecting a channel provides a sensible day default when mirrored activity exists

## Validation

- `python -m py_compile slack_mirror/service/app.py slack_mirror/service/api.py tests/test_app_service.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_app_service tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
