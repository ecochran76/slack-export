# Frontend Auth Bootstrap Provisioning

State: CLOSED
Roadmap: P02
Opened: 2026-04-13

## Scope

Add an explicit operator-only first-user bootstrap path for frontend auth:

- create a local frontend-auth user without reopening browser self-registration
- support safe password entry for both interactive and unattended usage
- keep the implementation on the existing `user-env` operator seam rather than inventing a parallel admin API

## Current State

- the shipped config template now defaults browser self-registration to `false`
- live validation warns when external publishing is configured and self-registration remains enabled
- `user-env provision-frontend-user` now exists as the bounded bootstrap path for the first local browser-auth user
- the command supports:
  - prompted password entry by default
  - env-backed password input through `--password-env`
  - password rotation for an existing user through `--reset-password`
- the underlying auth logic remains on the shared frontend-auth service seam; the CLI stays thin over that shared logic

## Remaining Work

- no open work remains in this slice
- future follow-up should open a new narrow child plan for:
  - invitation-based onboarding
  - multi-user admin management from the browser
  - secret-store-backed bootstrap instead of env or prompt entry

## Non-Goals

- adding a hosted admin UI
- exposing user creation through the public API or MCP
- reopening browser self-registration as the normal bootstrap path

## Acceptance Criteria

- an operator can create the first local frontend-auth user while `allow_registration` remains `false`
- the command supports a non-shell-history password path for unattended usage
- the docs and planning surfaces describe the operator bootstrap path clearly

## Definition Of Done

This plan is done when local frontend-auth onboarding no longer depends on temporary browser self-registration and the supported bootstrap path is wired into the repo docs and operator surfaces.
