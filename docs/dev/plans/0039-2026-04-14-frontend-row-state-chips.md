State: CLOSED
Date: 2026-04-14
Owner: Codex
Roadmap: P02

# 0039 - Frontend Row State Chips

## Why

The browser managers already show page-level banners and row-local error text, but successful or failed row mutations are still hard to scan in the table itself. A compact per-row outcome chip makes recent rename results visible without forcing users to reread the banner.

## Current State

Already shipped before this slice:
- inline rename/delete for reports and exports
- page-level success/error feedback
- row-local error blocks

Remaining gap before this slice:
- no compact per-row success/error state for recent rename attempts

## Scope

- add a small per-row outcome chip slot on report rows
- add a small per-row outcome chip slot on export rows
- show `saved` on successful rename
- show `error` on failed rename/delete
- clear stale row outcome state when retrying or canceling

## Non-Goals

- API changes
- delete-success row persistence after the row is removed
- broader visual redesign of the managers

## Acceptance Criteria

- report rows render a compact row-state chip slot
- export rows render a compact row-state chip slot
- rename success shows a positive row-state chip
- failed rename/delete shows an error row-state chip
- stale row-state chips clear on retry/cancel

## Validation

- `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_api_server -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
