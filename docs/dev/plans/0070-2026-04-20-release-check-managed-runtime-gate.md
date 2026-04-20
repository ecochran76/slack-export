# Release Check Managed Runtime Gate

State: CLOSED
Roadmap: P11
Opened: 2026-04-20
Closed: 2026-04-20

## Current State

- `P11` already has managed runtime validation, MCP stdio smoke, and concurrent MCP readiness probes in `user-env check-live`.
- `release check` currently validates repo-local release discipline, generated docs, planning audit, optional clean worktree, and optional release-version policy.
- `release check` does not yet have a release-gate switch that verifies the installed user-scoped runtime and MCP launcher.
- Operators therefore need to remember that a release signoff is two separate commands instead of one explicit repo-owned release gate.

## Scope

- Add an opt-in `release check --require-managed-runtime` gate.
- Have the gate run the managed install's `slack-mirror-user user-env check-live --json`.
- Keep the default `release check` repo-only so developer machines without a managed install are not blocked.
- Surface managed runtime failures through the same machine-readable release-check issue envelope.
- Update docs, tests, roadmap, and runbook.

## Non-Goals

- Do not change `user-env check-live` semantics.
- Do not make managed runtime validation mandatory for every local release check.
- Do not alter MCP tools.
- Do not run destructive install, update, rollback, or recovery commands.

## Acceptance Criteria

- CLI parser accepts `release check --require-managed-runtime`.
- `release_check(..., require_managed_runtime=True)` runs `slack-mirror-user user-env check-live --json`.
- Managed runtime failure becomes a release-check failure code.
- JSON output includes the managed runtime requirement flag.
- Tests cover parser dispatch and service success/failure behavior.
- Docs explain when to use the stronger release gate.

## Definition Of Done

- Code and generated docs updated.
- Tests pass.
- Planning audit passes.
- Runbook records validation evidence.

## Closeout

- Added `release check --require-managed-runtime`.
- The opt-in gate runs `slack-mirror-user user-env check-live --json`.
- Managed runtime failures surface as `MANAGED_RUNTIME_CHECK_FAILED`.
- JSON output includes `require_managed_runtime`.
- Updated README, user-install docs, roadmap, and the parent `P11` plan.
