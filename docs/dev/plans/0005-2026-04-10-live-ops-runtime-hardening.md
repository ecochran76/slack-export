# Live Ops Runtime Hardening

State: OPEN
Roadmap: P04
Opened: 2026-04-10

## Scope

Harden the supported live-service operating model into a stable operator contract:

- supported systemd topology
- daemon supervision and service health checks
- drift and duplicate-topology detection
- auth guardrail enforcement in live mode
- installer/status/runbook alignment for unattended operation

## Current State

- the supported two-service topology per workspace is documented
- live-mode install and status scripts exist
- `slack-mirror user-env validate-live` now checks the managed live contract for config, DB, workspace sync, explicit outbound write tokens, expected active units, and duplicate legacy topology
- validator output now includes stable failure classes and recovery hints
- `user-env install` and `user-env update` now run a managed-runtime validation gate for config, DB, workspace sync, and API service health
- remaining work is broader operator smoke coverage and any deeper queue-freshness heuristics that should become part of the supported contract

## Parallel Tracks

### Track A | Runtime Topology And Supervision

- one supported long-lived topology per workspace
- service unit expectations
- restart and recovery behavior

### Track B | Drift Detection And Health

- duplicate-topology detection
- queue freshness and backlog checks
- operational status surfaces and failure classification

### Track C | Operator Workflow

- install/update validation
- auth guardrail expectations
- runbook and script alignment

## Critical Path

- settle the operator contract for the supported runtime topology first
- then tighten detection, validation, and troubleshooting surfaces around that contract

## Non-Goals

- alternative runtime managers beyond the documented supported path
- distributed or multi-host orchestration
- broad platform packaging work unrelated to live operations

## Acceptance Criteria

- the supported live topology is explicit and enforced by docs and scripts
- duplicate writers and stale-service drift are detectable through supported status paths
- auth and write-token expectations for live installs are explicit
- operator docs, installer behavior, and status checks describe the same runtime contract

## Definition Of Done

This plan is done when unattended live operation can be installed, validated, and debugged through one coherent operator workflow rather than a mix of scripts, tribal knowledge, and partial runbooks.
