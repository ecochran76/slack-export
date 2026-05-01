# 0149 | Receipts reference child boundary review

State: CLOSED

Roadmap: P12

## Context

Receipts homework H6 asks Slack Export to remain the reference child service for
Slack runtime, search, evidence, reports, events, tenant management, and
Slack-native projection while not becoming the shared parent UI. This is a
boundary and handoff slice after H1-H5 landed.

## Current State

Shipped baseline:

- H1 added the Slack-owned Receipts compatibility smoke gate.
- H2 hardened `/v1/service-profile` as the contract authority.
- H3 deepened event readiness, stale cursor guidance, and export lifecycle
  events.
- H4 pinned child-owned identity/display rendering and raw provenance.
- H5 added tenant-maintenance route/action discovery and per-tenant
  `maintenance_actions`.

Shipped in this slice:

- Closed the original Receipts homework note.
- Recorded the boundary decision that Receipts owns the shared parent UX while
  Slack Export owns Slack runtime/search/projection/tenant semantics.
- Added a consolidated Slack-to-Receipts handoff covering H1-H5 commits,
  contract fields, validation, and remaining parent-side adaptation.

Remaining work:

- Receipts should consume the H1-H5 Slack contracts through its parent BFF and
  run Slack's compatibility smoke gate in its own integration checklist.
- Slack Export should keep `/operator` and Python-rendered pages as child
  proving/operator surfaces, not cross-service frontend authority.

## Scope

- Review the boundary from `docs/dev/notes/0007-2026-05-01-receipts-dev-state-homework.md`.
- Add one concise Receipts-facing handoff note.
- Update roadmap and runbook wiring.

## Non-Goals

- Do not add new Slack runtime behavior in this slice.
- Do not edit Receipts from this repo.
- Do not move Slack-owned search, sync, DB, tenant, or projection logic into the
  parent frontend.

## Acceptance

- H6 boundary is documented as closed.
- Receipts has one handoff note with commit hashes, changed contract fields,
  validation evidence, residual risks, and parent-side next steps.
- Planning audit remains green.

## Validation

Passed:

- `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git diff --check`

## Next Recommended Action

Pause Slack Export convergence work until the Receipts agent consumes this
handoff, then use Receipts feedback to choose the next Slack-owned contract
slice instead of adding speculative parent-UI behavior here.
