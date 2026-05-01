# 0009 | Receipts H1-H6 contract handoff

Date: 2026-05-01
From: Slack Export / Slack Mirror
Audience: Receipts maintainers

## Context

Slack Export completed the Receipts homework in
`docs/dev/notes/0007-2026-05-01-receipts-dev-state-homework.md`.

Receipts should treat Slack Export as the reference Slack child service, not as
the shared parent UI. Slack Export owns Slack sync, database, tenant setup,
projection, search, event/status semantics, identity rendering, artifact
storage, and Slack-native guardrails. Receipts owns the shared search workbench,
report creation UX, bulk result actions, guest links, evidence inspector, live
view, and cross-child shell.

## Completed Commits

- `b58bc25 test(receipts): add compatibility smoke gate`
- `2660eb3 test(receipts): harden service profile contract`
- `8271a09 test(receipts): pin identity display fixtures`
- `3521b03 feat(receipts): deepen event readiness lifecycle`
- `b035ee5 feat(receipts): expose tenant maintenance capabilities`

Related handoff-only commit:

- `0e224cf docs(receipts): hand off compatibility smoke gate`

## Contract Fields Added Or Hardened

- `GET /v1/service-profile`
  - `ui.surfaceOwnership`
  - `guestGrants.routes`
  - `guestGrants.localOnlyRoutes`
  - `events`
  - `eventDescriptors`
  - `capabilities.eventStatus`
  - `capabilities.eventFollow: false`
  - `tenantMaintenance`

- `GET /v1/events`
  - cursor-backed event rows with snake_case aliases
  - `oldestCursor`
  - `latestCursor`
  - stale cursor detection
  - child-owned recovery guidance

- `GET /v1/events/status`
  - current, empty, and filtered-empty status states
  - event family counts
  - oldest/latest cursor metadata
  - cursor retention metadata
  - child-owned recovery guidance

- selected-result and context payloads
  - guest-safe display text via `matched_text` / rendered text lanes
  - raw Slack text preserved under raw/provenance fields
  - `text_rendering` metadata when display rendering differs
  - human sender/channel labels when Slack Export knows a safe label

- tenant status and maintenance
  - `/v1/tenants`
  - `/v1/tenants/{tenant}`
  - per-tenant `maintenance_actions`
  - redacted credential readiness/presence
  - DB stats, backfill status, live unit state, health, and next action
  - action enabled/disabled reasons, danger flags, typed confirmation values,
    concrete paths, methods, and default body templates

## Validation Evidence

Slack Export validation passed after H5:

```bash
./.venv/bin/python scripts/smoke_receipts_compatibility.py --json
./.venv/bin/python scripts/smoke_receipts_compatibility.py --base-url http://127.0.0.1:8787 --query "website service" --json
python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json
git diff --check
```

Observed live child API state after install/restart:

- `GET http://127.0.0.1:8787/v1/health` returned `{"ok": true}`.
- live Receipts compatibility smoke returned `ok: true`.
- live `/v1/service-profile` advertised `tenantMaintenance.actionField:
  maintenance_actions` and action ids `onboard`, `install_credentials`,
  `activate`, `start_live_sync`, `restart_live_sync`, `stop_live_sync`,
  `run_initial_sync`, and `retire`.

## Remaining Parent-Side Adaptation

- Receipts should call Slack Export's smoke gate from its Slack compatibility
  checklist before enabling new parent-side Slack UX behavior.
- Receipts should consume `/v1/service-profile` as the authority for Slack route
  templates and feature gates.
- Receipts should render shared search/report/evidence/live-view UX from JSON
  contracts, not by scraping `/settings/tenants`, `/operator`, or Slack-native
  display fields.
- Receipts should proxy tenant mutations only through child-session,
  same-origin Slack routes and honor Slack-provided `maintenance_actions`
  instead of re-implementing action availability.
- Receipts should keep guest grants limited to Slack-declared artifact/report
  read routes; search, artifact listing, creation, rename, delete, runtime
  reports, tenant actions, and workspace management stay child-session only.

## Residual Risks

- `eventFollow` remains intentionally false until Slack Export implements a real
  follow/SSE/streaming route.
- The tenant action labels may need UX wording refinement once Receipts has the
  concrete settings layout, but action availability and danger semantics should
  stay Slack-owned.
- Future shared-library extraction should wait until at least two child repos
  prove compatible selected-result/report artifacts for the same workflow.

## Next Recommended Action

Receipts should consume this handoff in its Slack compatibility checklist, wire
the Slack adapter to the hardened profile/tenant/event contracts, and run the
Slack-owned compatibility smoke gate from the Receipts repo before shipping new
parent-side Slack surfaces.
