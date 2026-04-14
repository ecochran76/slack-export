State: CLOSED
Date: 2026-04-14
Owner: Codex
Roadmap: P02

# 0037 - Frontend Field-Level Create Errors

## Why

The browser create forms already block invalid submissions, mark the failing field, and focus it. The remaining usability gap is that the message still lives mainly in the shared form error block. This slice adds field-level error slots and helper text so users can see exactly what is wrong next to the relevant input.

## Current State

Already shipped before this slice:
- local create validation on `/runtime/reports` and `/exports`
- invalid-field styling on the specific failing field
- focus movement to the first invalid field
- shared form-level create error regions

Remaining gap before this slice:
- users still have to map the shared error text back to the field
- the forms do not yet expose field-local helper/error slots for the create flow

## Scope

- add field-level helper and error slots for report create inputs
- add field-level helper and error slots for export create inputs
- wire invalid-state messaging to those field-local slots
- preserve the existing form-level create error block as summary feedback

## Non-Goals

- server-side validation changes
- redesign of the browser managers
- row-level mutation error behavior

## Acceptance Criteria

- invalid report create attempts show the message next to the failing field
- invalid export create attempts show the message next to the failing field
- relevant inputs continue to clear stale invalid state and field-local errors as the user edits
- form-level create error blocks remain available as secondary context

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
