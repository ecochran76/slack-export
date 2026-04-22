# 0120 | React Action Ergonomics Polish

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React operator preview exposes tenant action parity for credential
installation, activation, initial sync, live-sync start/restart/stop, bounded
maintenance backfill, and guarded tenant retirement. Authenticated browser QA
under `0119` showed the actions were functionally present, but rendered cards
mixed routine maintenance with guarded stop/retire controls and the compact
table cramped the details column.

## Scope

- Add neutral action-intent grouping to `ActionButtonGroup`.
- Map tenant actions into next-step, maintenance, and guarded groups.
- Improve rendered density for action buttons and the compact tenant table.
- Re-run rendered browser QA with screenshots and overflow checks.

## Non-Goals

- No new tenant API routes or mutation semantics.
- No Slack-specific behavior inside reusable frontend primitives.
- No route migration of the production Python tenant settings page.

## Acceptance Criteria

- Tenant cards visually separate primary/next-step actions, routine
  maintenance, and guarded stop/retire controls.
- Compact table details remain inspectable without visually clipping the
  details affordance at desktop width.
- Desktop and mobile rendered QA show no page-level horizontal overflow.
- Typecheck, build, docs checks, and planning audit pass.

## Definition Of Done

- Implementation and docs are committed on the dedicated frontend branch.
- `agent-browser` screenshots are captured for the rendered operator page.
- Closeout records validation evidence and the next best recommendation.
