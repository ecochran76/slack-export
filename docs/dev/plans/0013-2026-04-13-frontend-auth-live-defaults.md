# Frontend Auth Live Defaults

State: CLOSED
Roadmap: P02
Opened: 2026-04-13

## Scope

Tighten the default browser-auth posture for externally exposed live installs:

- new installs default to closed self-registration
- live validation warns when an external-facing install explicitly leaves self-registration enabled

## Current State

- the browser-auth baseline and follow-up hardening slices are already shipped through `0009` to `0012`
- the shipped config template now defaults `service.auth.allow_registration` to `false`
- live validation now warns when:
  - frontend auth is enabled
  - an external export base URL is configured
  - browser self-registration remains enabled
- explicit allowlisted or open self-registration remains overrideable, but no longer hides as the default posture

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - making the external self-registration warning stricter or policy-aware
  - different defaults for local-only vs externally published installs
  - bootstrapping flows for first-user setup without temporary open registration

## Non-Goals

- removing the ability to enable self-registration explicitly
- introducing a hosted admin or invitation system
- forcing existing user configs to change silently

## Acceptance Criteria

- new config templates default to closed self-registration
- `validate-live` warns when an externally exposed install explicitly leaves self-registration enabled
- the docs and runbook reflect the tighter default posture

## Definition Of Done

This plan is done when live browser auth defaults are stricter for new installs and the operator validation surface flags externally exposed self-registration as an intentional exception.
