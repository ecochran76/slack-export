State: CLOSED
Date: 2026-04-14
Owner: Codex
Roadmap: P02

# 0038 - Frontend Create Helper Consolidation

## Why

The report and export browser create forms had converged functionally, but they were still carrying duplicated field-state, field-error, and focus helper logic in separate inline script blocks. That duplication makes the next browser-form slice riskier than it needs to be.

## Current State

Already shipped before this slice:
- client-side create validation
- field-invalid styling
- focus movement to the first invalid field
- field-local helper and error slots

Remaining gap before this slice:
- report and export create forms still duplicated the same browser helper logic

## Scope

- factor the shared create-field helper logic through one Python-side renderer
- preserve the current browser function names and behavior for both forms
- keep the report/export create contract unchanged

## Non-Goals

- redesign of browser form markup
- API contract changes
- broader frontend bundling or asset-pipeline work

## Acceptance Criteria

- report and export create forms continue to expose the same browser helper names and behavior
- the duplicated inline helper logic is replaced by one shared server-side generator
- targeted browser/API regression tests still pass

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
