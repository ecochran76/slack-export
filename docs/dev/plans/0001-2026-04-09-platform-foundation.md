# Platform Foundation

State: CLOSED
Roadmap: P01
Opened: 2026-04-09
Supersedes: `docs/dev/PHASE_1_PLATFORM_FOUNDATION.md`

## Scope

Make the repo operable under one coherent planning and platform-foundation contract:

- one supported runtime topology
- one canonical install/upgrade planning path
- one canonical release-planning path
- one documented service-boundary planning path

## Current State

- the deterministic planning contract is in place and wired through `ROADMAP.md`, `RUNBOOK.md`, and `docs/dev/plans/`
- the supported runtime topology, installer path, and service-boundary work now have active child plans under `P01`, `P02`, and `P04`
- the repo has moved off the older `PHASE_*` planning files as active sources of truth
- the repo now has a supported `slack-mirror release check` gate for version/docs/planning validation
- the installer and live-ops child lanes have now closed cleanly, and future work can proceed through bounded child plans without relying on the older `PHASE_*` planning files
- this coordination plan is closed on that planning and platform-foundation baseline

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
