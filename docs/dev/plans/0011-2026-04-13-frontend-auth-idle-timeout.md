# Frontend Auth Idle Timeout

State: CLOSED
Roadmap: P02
Opened: 2026-04-13

## Scope

Add a bounded inactivity timeout to the shipped browser-auth session baseline:

- config-backed idle timeout on top of absolute session expiry
- idle-expiry enforcement in shared session resolution
- idle-expiry visibility in session listing and auth status

## Current State

- the local frontend-auth baseline and login throttling slices are already shipped through `0009` and `0010`
- browser sessions now expire on inactivity through a config-backed timeout in addition to absolute expiry
- the inactivity policy is enforced through the shared auth service boundary, not only at the browser route layer
- `/auth/status` now reports the configured idle timeout
- `/auth/sessions` now marks stale sessions with `idle_expired`

## Remaining Work

- no open work remains in this slice
- future auth follow-up should open a new narrow child plan for:
  - sliding absolute expiry or refresh-token style session models
  - IP/device-aware session policy
  - stronger abuse controls beyond the current bounded browser-auth seam

## Non-Goals

- introducing refresh tokens
- moving auth state out of SQLite
- building a provider-backed identity model

## Acceptance Criteria

- a session with stale `last_seen_at` is rejected by the shared auth resolver
- `/auth/status` exposes the configured idle timeout
- `/auth/sessions` distinguishes absolute expiry from idle expiry

## Definition Of Done

This plan is done when browser-auth sessions have a bounded inactivity timeout that is enforced and visible through the existing auth service and API contract.
