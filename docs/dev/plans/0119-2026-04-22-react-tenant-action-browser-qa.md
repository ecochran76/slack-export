# 0119 | React Tenant Action Browser QA

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench now has action parity for credential installation,
activation, initial sync, live-sync start/restart/stop, guarded retirement, and
bounded maintenance backfill. Before adding more tenant controls, the migrated
surface needs browser QA against the authenticated API-served React build.

## Scope

- Smoke `/operator` through the authenticated Python API service.
- Verify card and table views render current tenants.
- Verify protected tenants do not expose `Retire tenant`.
- Verify non-protected tenants expose guarded retirement.
- Verify stop-live and retire confirmations require typed tenant names.
- Verify the mirrored-DB deletion checkbox is explicit and unchecked by
  default.
- Verify responsive layout avoids page-level horizontal overflow.

## Non-Goals

- Do not execute real live-sync, backfill, credential, activation, or retire
  mutations.
- Do not change frontend behavior.
- Do not expand action semantics.

## Acceptance Criteria

- `default`, `soylei`, and `pcg` render in card/table views.
- `default` and `soylei` hide `Retire tenant`; `pcg` shows it.
- Stop-live confirmation stays disabled until the exact tenant name is typed.
- Retire confirmation stays disabled until the exact tenant name is typed.
- Retire confirmation shows an unchecked mirrored-DB deletion option.
- Desktop and mobile screenshots are captured.

## QA Evidence

- Desktop table screenshot:
  `/tmp/slack-operator-qa/operator-table-desktop.png`
- Mobile screenshot:
  `/tmp/slack-operator-qa/operator-mobile.png`
- Browser DOM check reported three tenants and no page-level horizontal
  overflow at desktop and mobile widths.
- No real tenant mutation was confirmed or executed.

## Definition Of Done

- QA evidence is recorded in `RUNBOOK.md`.
- `ROADMAP.md` records that action-parity browser QA is complete.
- The QA slice is committed independently.
