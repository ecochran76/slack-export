# 0106 | Neutral Detail Panel Primitive

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench already has expandable tenant diagnostics in both
the card and compact table views. Before this slice, those disclosures were
implemented directly in the tenant workbench with separate tenant/table CSS
contracts.

This slice adds a local provider-neutral disclosure primitive while keeping the
actual diagnostics content Slack-specific and repo-local.

## Scope

- Add a reusable `DetailPanel` component for native disclosure rendering.
- Support the two currently proven presentation variants:
  - `card` for wider row diagnostics with optional summary metadata.
  - `compact` for table-cell inspection affordances.
- Move tenant card and table detail disclosures onto the primitive.
- Update frontend contract documentation and roadmap wiring.

## Non-Goals

- Do not extract a shared package yet.
- Do not add persisted open/closed state.
- Do not add route-synchronized expansion state.
- Do not change tenant status data, polling, or action behavior.

## Acceptance Criteria

- Tenant cards still expose live-unit, text/embedding, and semantic-readiness
  diagnostics behind a disclosure.
- Tenant table rows still expose the compact `Inspect` disclosure.
- The primitive uses provider-neutral names and does not import tenant types.
- Existing frontend validation and browser smoke pass.

## Definition Of Done

- `frontend/src/components/DetailPanel.tsx` exists and is used by
  `TenantWorkbench`.
- Tenant-specific disclosure selectors are replaced with neutral
  `detail-panel` selectors.
- `docs/dev/FRONTEND_CONTRACTS.md`, `ROADMAP.md`, and `RUNBOOK.md` are updated.
- The slice is committed independently.
