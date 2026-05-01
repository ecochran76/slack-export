# 0147 | Receipts event readiness lifecycle

State: CLOSED

Roadmap: P12

## Context

Receipts homework H3 asks Slack Export to make event readiness behave like an
operator contract, not only a list endpoint. Receipts Live View needs to explain
current, empty, filtered-empty, degraded, behind, and stale-cursor states without
scraping logs or parsing Slack-native tables.

## Current State

Shipped baseline:

- `/v1/events` exposes cursor-backed Slack-owned committed product events.
- `/v1/events/status` exposes descriptors, event counts, latest cursor, and
  per-event-type watermarks.
- `eventFollow` remains false in `/v1/service-profile`.

Shipped in this slice:

- Added explicit oldest/newest cursor metadata and stale-cursor recovery
  guidance.
- Added event family counts and clearer empty/filter status semantics.
- Added Slack-owned artifact lifecycle events for export rename and delete.
- Documented cursor retention/stale cursor behavior.

Remaining work:

- Keep `eventFollow: false` until there is a real follow/SSE/streaming route.
- Consider guest artifact read/open events later only if they can be emitted
  without exposing guest secrets or private artifact bodies.

## Scope

- Extend the existing event/status payloads in `slack_mirror.service.app`.
- Persist export rename/delete lifecycle events in the export root.
- Add tests for cursor status, filtering, rename/delete lifecycle events, and
  API status payload shape.
- Update docs, roadmap, and runbook.

## Non-Goals

- Do not add SSE/follow streaming; keep `eventFollow: false`.
- Do not expose guest secrets or artifact body text in event payloads.
- Do not introduce a second event store for Slack message/file observed events.

## Acceptance

- `/v1/events/status` exposes oldest/latest cursor metadata, family counts,
  filtered-empty/empty/current statuses, and recovery guidance.
- `/v1/events` marks stale cursors and provides reset guidance.
- Export rename/delete mutations create child-owned lifecycle events.
- Event tests cover tenant/account filters, event type filters, cursor paging,
  stale cursor behavior, privacy, and limit.

## Validation

Passed:

- `./.venv/bin/python -m py_compile slack_mirror/service/app.py slack_mirror/service/api.py tests/test_app_service.py tests/test_api_server.py`
- `./.venv/bin/python -m unittest tests.test_app_service.AppServiceTests.test_list_child_events_pages_committed_events_with_opaque_cursors tests.test_api_server.ApiServerTests.test_events_endpoint_pages_committed_child_events tests.test_api_server.ApiServerTests.test_service_profile_receipts_contract_is_stable -v`
- `./.venv/bin/python scripts/smoke_receipts_compatibility.py --json`
- `/home/ecochran76/.local/share/slack-mirror/venv/bin/python -m pip install -e /home/ecochran76/workspace.local/slack-export`
- `systemctl --user restart slack-mirror-api.service && sleep 1 && curl -sS http://127.0.0.1:8787/v1/health`
- `./.venv/bin/python scripts/smoke_receipts_compatibility.py --base-url http://127.0.0.1:8787 --query "website service" --json`
- `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git diff --check`

## Next Recommended Action

After H3 lands, continue H5 by exposing a narrow tenant-maintenance capability
surface for Receipts settings pages.
