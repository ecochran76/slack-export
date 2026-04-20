# Stable MCP-Capable User-Scoped Release

State: OPEN
Roadmap: P11
Opened: 2026-04-18

## Scope

Harden the current product into the first stable user-scoped release where:

- `user-env install` and `user-env update` are repeatable
- managed services remain healthy after install, update, and restart
- MCP is a reliable supported operator interface
- release readiness can be evaluated by explicit repo-owned checks

This plan covers:

- user-scoped installer and updater reliability
- managed-service health and bounded recovery expectations
- MCP usability, contract hardening, and operator-facing error quality
- release validation gates and smoke coverage
- documentation updates required to make the supported path obvious

This plan does not include:

- the cross-repo operator-frontend migration under `P09`
- post-release semantic retrieval modernization under `P10`
- a broad redesign of search quality, embeddings, or reranking
- a major deployment-model change away from the current user-scoped managed install

## Current State

- the repo already ships user-scoped install, update, rollback, live validation, managed services, browser auth, and MCP entrypoints
- recent slices repaired several regressions that would block release confidence:
  - managed update path resolution
  - auth-safe runtime-report snapshot generation
  - durable reconcile state after bounded backfill
- the first `P11` slice is landed:
  - `user-env status`, `user-env check-live`, and shared runtime status now include real MCP smoke readiness instead of only launcher presence
- the next `P11` slice is also landed:
  - managed runtime-report unit files and active timer scheduling are now part of the managed-runtime gate
  - `recover-live` can safely refresh managed install artifacts when launcher or unit drift is detected
- the next `P11` slice is also landed:
  - clean-state install no longer fails on a missing configured dotenv file
  - managed-runtime bootstrap validation no longer blocks on workspace credentials before config editing
  - disposable-home rehearsal now matches the intended contract: install/update pass, while `check-live` remains the stricter post-onboarding gate
- the next `P11` slice is also landed:
  - `user-env status` and `user-env check-live` now include a bounded concurrent MCP readiness probe instead of validating only a single stdio client
  - the shared lightweight runtime status surface now exposes concurrent MCP readiness state so API and MCP callers can see the same release gate
- the next `P11` slice is also landed:
  - `release check --require-managed-runtime` combines repo-local release discipline with the installed `slack-mirror-user user-env check-live --json` gate
  - the stronger release gate is opt-in so repo-only development machines and CI are not blocked by the absence of a managed user install
  - managed runtime failures now surface through the same release-check issue envelope as docs, planning, version, and worktree failures
- the current baseline is functional, but the product still lacks one bounded release lane that treats install/update, managed-runtime health, and MCP usability as one coordinated target
- MCP exists, but it is not yet clearly validated as a stable release interface with explicit readiness criteria, bounded failure modes, and strong operator guidance
- the user wants this worktree to focus on the stable release line, while frontend migration proceeds separately in its own worktree

## Target Outcome

The release should be boring in the right ways:

- install works from the documented path
- update works without leaving a broken managed snapshot
- managed services restart cleanly and expose actionable health state
- MCP returns predictable machine-readable successes and failures
- operators have one explicit release gate and one explicit recovery path

## Subprojects

### 1. Installer And Updater Reliability

- confirm the supported install path from clean state
- harden managed app snapshot creation and update semantics
- verify rollback and repair behavior when update or service state drifts

### 2. Managed Service Health

- validate API, daemon, live ingress, and runtime-report services after install and restart
- tighten service-health diagnostics and bounded recovery expectations
- ensure service failures surface actionable operator hints instead of raw tracebacks

### 3. MCP Contract Usability

- audit current MCP tools and arguments against real operator tasks
- harden machine-readable error behavior and precondition handling
- document what MCP is supported to do in the release baseline

### 4. Release Validation And Smoke Coverage

- define the release gate for a user-scoped install
- make `check-live` and adjacent checks sufficient for release confidence
- add or refine focused smoke coverage for installer, managed runtime, and MCP paths

### 5. Docs And Operator Workflow

- tighten the canonical install and update docs
- make MCP usage discoverable and precise
- keep README, user-install, CLI, and runbook guidance aligned with the supported release path

## Likely Slice Order

1. audit and tighten the release gate plus current failure modes
2. installer/updater hardening where the gate still fails or is ambiguous
3. MCP usability and contract-hardening slice
4. docs and release-check closure

## Acceptance Criteria

- roadmap and runbook explicitly track this release-hardening lane
- a bounded child plan exists for the lane before implementation proceeds
- the supported user-scoped release path is documented clearly enough to execute from scratch
- release readiness is defined by explicit commands and health checks
- MCP is treated as a supported interface with concrete usability and reliability expectations

## Validation Plan

- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- wiring review:
  - ensure `P11` references this plan
  - ensure the runbook records the new release-hardening lane and why it was opened
