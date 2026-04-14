# Frontend Auth Hardening

State: CLOSED
Roadmap: P02
Opened: 2026-04-13

## Scope

Harden the shipped local browser-auth baseline without expanding it into a hosted account system:

- make frontend-auth registration status less misleading for allowlisted installs
- add bounded failed-login throttling at the shared service boundary

## Current State

- the local frontend-auth baseline from `0009` is already shipped
- `/auth/status` now distinguishes:
  - unrestricted registration
  - allowlisted registration
  - closed registration
- bounded failed-login throttling is now shipped through the shared service and API boundary:
  - config-backed window and threshold
  - DB-backed failed-attempt tracking
  - stable `429 RATE_LIMITED` responses from `/auth/login`
- the hardening remains intentionally narrow:
  - no provider-backed auth
  - no CAPTCHA
  - no broad hosted-account feature set

## Remaining Work

- no open work remains in this hardening slice
- future auth follow-up should open a new narrow child plan for:
  - idle-session expiry or rolling-session policy
  - brute-force protection beyond simple per-identity throttling
  - broader registration or provider-backed identity changes

## Non-Goals

- importing the broader `../litscout` hosted auth model
- building a full abuse-prevention stack
- protecting every API route behind frontend auth

## Acceptance Criteria

- `/auth/status` no longer reports allowlisted installs as fully open registration
- repeated failed `/auth/login` attempts return a stable throttling error
- the throttling contract is documented in config and API docs

## Definition Of Done

This plan is done when the browser-auth baseline has bounded failed-login throttling and clearer registration-policy semantics without reopening the broader service-surface lane.
