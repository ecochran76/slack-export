# Frontend Auth Baseline

State: OPEN
Roadmap: P02
Opened: 2026-04-13

## Scope

Add a bounded local-auth baseline for browser-facing Slack Mirror surfaces:

- local username/password registration and login
- cookie-backed browser sessions
- protection for published browser/report/export routes
- minimal auth API and login/register HTML entry pages

## Current State

- local username/password auth is now shipped through:
  - `/auth/status`
  - `/auth/session`
  - `/auth/register`
  - `/auth/login`
  - `/auth/logout`
  - `/login`
  - `/register`
- browser-facing export and runtime-report surfaces are now protected when frontend auth is enabled
- the browser root `/` now serves an authenticated landing page over runtime status, runtime reports, and recent exports
- `/settings` now serves a browser-facing account page over frontend-auth policy and current-user sessions
- `cookie_secure_mode` is shipped, with live HTTPS ingress verified through the cooper reverse-proxy path
- browser auth POST routes are now same-origin guarded through `Origin`/`Referer` validation
- current-user session listing and per-session revocation are now shipped through the browser auth API
- self-registration can now be restricted to an explicit allowlist of normalized usernames, including email-style usernames
- the correct scope remains narrower than `../litscout`:
  - keep the local-password plus cookie-session shape
  - do not import a broader hosted product/account/subscription model

## Remaining Work

- tighten browser-session hardening:
  - session presentation and revocation UX beyond the raw JSON/auth API contract
- decide whether allowlisted self-registration should remain enabled by default for live installs
- add any further browser polish without expanding into a full hosted app shell

## Parallel Tracks

### Track A | Persistence And Service

- auth tables and migrations
- password hashing
- session issuance and revocation

### Track B | Browser And API Contract

- login/register HTML pages
- auth JSON routes
- protected export/runtime-report browsing

## Non-Goals

- building a full hosted app shell
- adding OAuth providers in the first slice
- protecting every operator/API route indiscriminately

## Acceptance Criteria

- an allowed local user can register and sign in through the browser
- protected browser/report/export routes require a valid auth session
- unauthenticated HTML requests redirect to `/login`
- unauthenticated protected JSON requests fail with a stable auth error

## Definition Of Done

This plan is done when published browser-facing Slack Mirror surfaces no longer default to anonymous access, and the shipped auth baseline is a narrow local-password/cookie-session seam that future provider work can extend without replacing.
