# 0145 | Receipts service-profile contract hardening

State: CLOSED

Roadmap: P12

## Context

Receipts homework H2 asks Slack Export to treat `GET /v1/service-profile` as
the contract authority for parent UI routing and feature gating. The profile
already exists and is consumed by Receipts, but its test coverage is mixed into
a broad API smoke test and does not explicitly freeze every Receipts-facing
contract field.

## Current State

Shipped baseline:

- `/v1/service-profile` advertises child-session auth, search/context routes,
  selected-result artifact lifecycle routes, event descriptors/status,
  guest-grant route policy, source metadata hints, and UI controls.
- `docs/API_MCP_CONTRACT.md` documents the profile's major fields.
- H1 added a compatibility smoke gate that exercises the profile as part of a
  wider Receipts-facing flow.

Shipped in this slice:

- Added dedicated service-profile contract tests for Receipts-required fields.
- Made UI ownership explicit enough that Receipts can distinguish parent-owned
  shared UX from child-owned Slack maintenance/runtime controls.
- Documented the new ownership metadata.

Remaining work:

- Continue H4 identity/display fixture coverage, including emoji rendering and
  unresolved/redacted/bot-authored cases.

## Scope

- Add a stable `ui.surfaceOwnership` contract to `/v1/service-profile`.
- Add targeted tests for routes, guest grants, event descriptor/status
  metadata, source metadata, and UI ownership flags.
- Update API documentation, roadmap, and runbook.

## Non-Goals

- Do not expose experimental browser pages as durable Receipts integration
  routes.
- Do not implement tenant-maintenance action capability schemas here; that is
  H5.
- Do not move Slack-owned sync/search/storage logic into Receipts.

## Acceptance

- A dedicated service-profile contract test catches Receipts-facing drift.
- The profile names parent-owned shared surfaces separately from child-owned
  Slack maintenance/runtime surfaces.
- Existing H1 compatibility smoke remains green.

## Validation

Passed:

- `./.venv/bin/python -m unittest tests.test_api_server.ApiServerTests.test_service_profile_receipts_contract_is_stable -v`
- `./.venv/bin/python scripts/smoke_receipts_compatibility.py --json`
- `./.venv/bin/python -m py_compile slack_mirror/service/api.py tests/test_api_server.py scripts/smoke_receipts_compatibility.py`
- `/home/ecochran76/.local/share/slack-mirror/venv/bin/python -m pip install -e /home/ecochran76/workspace.local/slack-export`
- `systemctl --user restart slack-mirror-api.service && sleep 1 && curl -sS http://127.0.0.1:8787/v1/service-profile`
- `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git diff --check`

## Next Recommended Action

After H2 lands, continue H4 identity/display fixture coverage so Slack-owned
labels, raw provenance, and emoji rendering are pinned for Receipts cards and
evidence inspectors.
