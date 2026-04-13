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

- the repo already serves browser-facing HTML at `/exports/*` and `/runtime/reports*`
- those surfaces are currently unauthenticated
- the repo has no hosted frontend shell or user-account model today
- the correct baseline is narrower than `../litscout`:
  - copy the local-password plus cookie-session shape
  - do not import its broader hosted product/account/subscription model

## Remaining Work

- add auth persistence to the canonical SQLite DB
- add shared service methods for register/login/logout/session resolution
- gate browser-facing routes while leaving health and Slack ingress semantics intact
- document config, route, and operator behavior

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

- a local user can register and sign in through the browser
- protected browser/report/export routes require a valid auth session
- unauthenticated HTML requests redirect to `/login`
- unauthenticated protected JSON requests fail with a stable auth error

## Definition Of Done

This plan is done when published browser-facing Slack Mirror surfaces no longer default to anonymous access, and the shipped auth baseline is a narrow local-password/cookie-session seam that future provider work can extend without replacing.
