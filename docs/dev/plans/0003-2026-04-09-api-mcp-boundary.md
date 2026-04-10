# API MCP Boundary

State: OPEN
Roadmap: P02
Opened: 2026-04-09
Supersedes: `docs/dev/API_MCP_BOUNDARY.md`

## Scope

Define and harden the shared application-service boundary for CLI, API, MCP, and agent skills:

- ownership boundaries
- canonical service methods
- transport-surface responsibilities
- minimal read/write/operational contract

## Current State

- shared application-service methods exist in `slack_mirror.service.app`
- local API transport exists
- MCP transport exists
- live runtime validation is now exposed through both API and MCP on top of the shared service boundary
- live runtime validation now returns compact machine-readable status, code, and per-workspace queue fields in addition to human-readable summary lines
- API and MCP write/read failures now map through a shared machine-readable error envelope with stable codes, retryability, and operation context
- outbound write actions now return explicit idempotency and retry semantics through the shared service boundary instead of exposing only raw DB rows
- remaining work is to tighten the documented contract, error model, and operator expectations around the shipped baseline

## Parallel Tracks

### Track A | Core Ownership

- core responsibilities
- forbidden duplication
- routing/auth invariants

### Track B | Surface Contracts

- minimal API surface
- minimal MCP surface
- error and audit model

## Critical Path

- settle the core service boundary first
- then map API and MCP onto that same boundary

## Non-Goals

- rebuilding the already-implemented baseline API or MCP transports from scratch
- adding unrelated new surface capabilities before the existing contract is tightened

## Acceptance Criteria

- one shared ownership model exists for CLI, API, MCP, and skills
- the shipped API and MCP baseline are documented against the same service boundary
- write semantics, routing, and audit expectations are explicit

## Definition Of Done

This plan is done when future API/MCP work can proceed against one explicit shared contract instead of inventing ownership boundaries per slice, and the canonical planning docs match the implemented baseline already in the repo.
