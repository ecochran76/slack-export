# Frontend Invalid Field Styling

State: CLOSED
Roadmap: P02
Opened: 2026-04-14

## Scope

Add invalid-field styling and field-specific client-side cues to the browser create forms.

- keep the existing form-level create error slots
- keep the existing API validation contracts unchanged
- focus on visually identifying which input needs correction

## Current State

- `/runtime/reports` now highlights the invalid create field for missing name, base URL, or bad timeout
- `/exports` now highlights the invalid create field for missing workspace, channel, day, timezone, or audience
- invalid field styling clears as the relevant field changes
- successful create responses clear any stale invalid-field styling

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - inline per-field helper text instead of only a shared form-level error block
  - export-id client-side validation and styling
  - richer accessibility polish for error summaries and focus management

## Non-Goals

- changing server-side validation behavior
- changing inline row mutation flows
- introducing a frontend framework or design-system dependency

## Acceptance Criteria

- invalid runtime-report create submissions mark the relevant field visually before fetch
- invalid export create submissions mark the relevant field visually before fetch
- changing the affected field clears its invalid styling
- targeted API/browser tests lock the served invalid-field helpers and markers

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
