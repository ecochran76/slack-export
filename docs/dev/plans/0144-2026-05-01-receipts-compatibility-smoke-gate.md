# 0144 | Receipts compatibility smoke gate

State: CLOSED

Roadmap: P12

## Context

Receipts opened a parent-side compatibility checklist at
`../receipts/docs/dev/plans/0047-2026-05-01-slack-receipts-compatibility-checklist.md`
and points back to Slack Export's homework note:
`docs/dev/notes/0007-2026-05-01-receipts-dev-state-homework.md`.

The first requested Slack-owned item is H1: one validation command that
Receipts maintainers can run before parent integration work. It should exercise
the public Receipts-facing contract without relying on private live corpus
contents.

## Current State

Shipped baseline:

- `/v1/service-profile` advertises Receipts-facing profile, route, event, and
  guest-grant policy metadata.
- `/v1/events`, `/v1/events/status`, `/v1/context-window`, `/v1/exports`, and
  `/exports/{exportId}` exist and are used by Receipts.
- Guest-grant assertions are accepted for export artifact reads.

Shipped in this slice:

- Added `scripts/smoke_receipts_compatibility.py` with fixture-backed coverage.
- Added optional live-API mode for checking an already running child service.
- Ensured guest-grant assertions are explicitly rejected on non-artifact routes,
  including otherwise local/unprotected search routes.
- Documented the command for Receipts maintainers.

Remaining work:

- Receipts should call this Slack-owned gate from its parent-side compatibility
  checklist before enabling new Slack-backed parent UI behavior.

## Scope

- Create a single script under `scripts/` that returns structured pass/fail
  output.
- Cover service profile, events, event status, context window,
  selected-result export create/open, allowed guest artifact read, and denied
  guest access to local-only routes.
- Add tests that prove the script can run against fixture state and catches the
  guest-route boundary.

## Non-Goals

- Do not move Receipts BFF or browser smoke behavior into Slack Export.
- Do not depend on private live Slack corpus contents for the default gate.
- Do not make guest grants authorize search, list, create, rename, delete,
  runtime reports, tenant actions, or workspace management.

## Acceptance

- `python scripts/smoke_receipts_compatibility.py --json` passes from a clean
  checkout using seeded fixture state.
- Failures identify the failing surface: profile, events, context, artifact,
  or guest grants.
- The script can optionally check a configured live API with `--base-url`.
- Guest-grant assertions on `/v1/search/corpus`, `/v1/exports`, and
  `POST /v1/exports` are rejected.
- README/RUNBOOK/ROADMAP record the command and result.

## Validation

Passed:

- `./.venv/bin/python -m py_compile slack_mirror/service/api.py scripts/smoke_receipts_compatibility.py tests/test_api_server.py tests/test_receipts_compatibility_smoke.py`
- `./.venv/bin/python scripts/smoke_receipts_compatibility.py --json`
- `./.venv/bin/python -m unittest tests.test_api_server.ApiServerTests.test_guest_grant_headers_are_rejected_on_local_only_routes tests.test_receipts_compatibility_smoke.ReceiptsCompatibilitySmokeTests.test_fixture_smoke_gate_returns_structured_pass -v`
- `/home/ecochran76/.local/share/slack-mirror/venv/bin/python -m pip install -e /home/ecochran76/workspace.local/slack-export`
- `systemctl --user restart slack-mirror-api.service && sleep 1 && curl -sS http://127.0.0.1:8787/v1/health`
- `./.venv/bin/python scripts/smoke_receipts_compatibility.py --base-url http://127.0.0.1:8787 --query "website service" --json`

## Next Recommended Action

After this lands, hand the command back to Receipts so their checklist can call
the Slack-owned gate before enabling new parent-side Slack features.
