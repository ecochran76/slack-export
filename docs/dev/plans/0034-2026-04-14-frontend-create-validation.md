# Frontend Create Validation

State: CLOSED
Roadmap: P02
Opened: 2026-04-14

## Scope

Add bounded client-side validation for the runtime-report and export create forms before they submit to the API.

- keep the existing API validation and error envelopes unchanged
- focus on obviously invalid browser submissions
- reuse the existing form-local error slots instead of introducing a new browser state model

## Current State

- `/runtime/reports` now validates report name, base URL, and timeout before create submission
- `/exports` now validates workspace, channel, day, timezone, and audience before create submission
- invalid submissions render in the existing form-local error slots and do not issue the create request
- relevant input and select changes clear stale local create errors

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - field-specific inline validation messages
  - stronger export-id client-side validation beyond server enforcement
  - visual invalid-field styling alongside the form-local error block

## Non-Goals

- changing server-side validation semantics
- changing inline row mutation behavior
- introducing a frontend framework or schema-validation library

## Acceptance Criteria

- empty or invalid runtime-report create submissions are blocked before fetch
- empty or invalid export create submissions are blocked before fetch
- validation errors render in the existing form-local error slots
- targeted API/browser tests lock the served validation markers

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
