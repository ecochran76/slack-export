# Platform Foundation

State: OPEN
Roadmap: P01
Opened: 2026-04-09
Supersedes: `docs/dev/PHASE_1_PLATFORM_FOUNDATION.md`

## Scope

Make the repo operable under one coherent planning and platform-foundation contract:

- one supported runtime topology
- one canonical install/upgrade planning path
- one canonical release-planning path
- one documented service-boundary planning path

## Parallel Tracks

### Track A | Runtime And Installer

- supported runtime topology
- install/upgrade flow
- legacy unit migration rules

### Track B | Release Discipline

- versioning policy
- release checklist
- migration and rollback expectations

### Track C | Service Boundary

- shared application-service boundary for CLI, API, MCP, and skills

## Critical Path

- finalize the platform-foundation lane definition first
- keep installer and service-boundary work aligned to that lane

## Non-Goals

- major expansion of API, MCP, outbound, or listener capability beyond the baseline already present in the repo
- unrelated search-platform or export-specific roadmap work

## Acceptance Criteria

- the roadmap lane is explicit and bounded
- installer/upgrade work is tracked through a deterministic plan file
- service-boundary work is tracked through a deterministic plan file
- legacy planning docs are retained as context, not treated as the authoritative active plan set

## Definition Of Done

This plan is done when the platform-foundation lane has clearly bounded child plans, those plans are wired into `ROADMAP.md` and `RUNBOOK.md`, and future work can proceed without relying on the older `PHASE_*` planning files as the active source of truth.
