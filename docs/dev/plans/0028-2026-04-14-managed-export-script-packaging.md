# Managed Export Script Packaging

State: CLOSED
Roadmap: P02
Opened: 2026-04-14

## Scope

Fix managed export creation in installed `user-env` environments by shipping the repo `scripts` package into the built wheel.

- keep the existing export-create API and browser contract unchanged
- preserve the current `create_channel_day_export()` subprocess-based implementation
- ensure the installed wheel contains `scripts/export_channel_day.py` at the path the shared service expects

## Current State

- the built package now includes the top-level `scripts` package
- managed installs now ship `site-packages/scripts/export_channel_day.py`
- `create_channel_day_export()` now fails with an explicit missing-script error if that contract regresses again

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - moving export creation fully into package-owned functions instead of subprocess script dispatch
  - stronger packaging tests that inspect the built wheel contents directly
  - broader live CRUD smoke coverage across browser management flows

## Non-Goals

- rewriting the channel-day exporter into a new package-owned API
- changing export manifest semantics
- changing browser manager UX for exports

## Acceptance Criteria

- managed user-env installs include `scripts/export_channel_day.py`
- authenticated browser export creation succeeds in the installed environment
- the shared service path raises an explicit missing-script error if packaging regresses

## Validation

- `python -m py_compile slack_mirror/service/app.py`
- `./.venv/bin/python -m unittest tests.test_app_service tests.test_api_server tests.test_runtime_report -v`
- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- live throwaway create/rename/delete smoke on `http://slack.localhost` for:
  - one runtime report
  - one channel-day export
