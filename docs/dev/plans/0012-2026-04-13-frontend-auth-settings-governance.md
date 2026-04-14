# Frontend Auth Settings Governance

State: CLOSED
Roadmap: P02
Opened: 2026-04-13

## Scope

Expose the active browser-auth policy directly on the authenticated settings page:

- registration mode and allowlist state
- absolute session lifetime
- idle session timeout
- failed-login throttle window and threshold

## Current State

- the browser-auth baseline and hardening follow-ups are already shipped through `0009`, `0010`, and `0011`
- `/settings` now surfaces the active auth-governance policy directly in HTML instead of forcing operators to inspect `/auth/status`
- the settings view now exposes:
  - registration mode
  - allowlist count
  - absolute session lifetime
  - idle session timeout
  - failed-login throttle policy

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - changing live defaults for externally exposed installs
  - browser-side explanations or warnings based on stricter policy posture
  - richer security event history or audit surfaces

## Non-Goals

- changing live auth defaults in this slice
- adding a new operator API just for browser policy display
- introducing a separate hosted admin UI

## Acceptance Criteria

- `/settings` shows the active auth policy without requiring `/auth/status`
- the displayed values come from the existing shared auth status contract
- the slice is documented and wired as a closed `P02` child plan

## Definition Of Done

This plan is done when the browser settings page exposes the current auth governance posture clearly enough that operators do not need to inspect raw JSON for common policy questions.
