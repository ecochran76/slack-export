State: CLOSED
Date: 2026-04-14
Owner: Codex
Roadmap: P02

# 0036 - Frontend Create Accessibility Focus

## Why

The browser create forms already validate locally and mark invalid fields, but they still leave keyboard and screen-reader users to hunt for the failing input manually. The next bounded fix is to move focus to the first invalid field and associate that field with the local form error block.

## Current State

Already shipped before this slice:
- local create-error regions on `/runtime/reports` and `/exports`
- pre-submit client-side validation
- invalid-field styling on the specific failing input

Remaining gap before this slice:
- invalid submit does not move focus to the failing field
- create inputs are not explicitly associated with the local error region through `aria-describedby`

## Scope

- focus the first invalid create field on `/runtime/reports`
- focus the first invalid create field on `/exports`
- wire the relevant create inputs to the local error region with `aria-describedby`
- mark the local create error region with polite live-region semantics

## Non-Goals

- broad a11y redesign of the report/export managers
- field-specific inline helper text blocks
- server-side validation contract changes

## Acceptance Criteria

- invalid report create attempts focus the failing field
- invalid export create attempts focus the failing field
- create inputs expose `aria-describedby` to the matching local error block
- local error blocks use polite live-region semantics

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
