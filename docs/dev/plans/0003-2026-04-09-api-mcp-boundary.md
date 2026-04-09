# API MCP Boundary

State: PLANNED
Roadmap: P02
Opened: 2026-04-09
Supersedes: `docs/dev/API_MCP_BOUNDARY.md`

## Scope

Define the shared application-service boundary for CLI, API, MCP, and agent skills:

- ownership boundaries
- canonical service methods
- transport-surface responsibilities
- minimal read/write/operational contract

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

- implementing the full API server
- implementing the full MCP server
- adding new surface capabilities beyond the documented boundary

## Acceptance Criteria

- one shared ownership model exists for CLI, API, MCP, and skills
- the minimum API and MCP contracts are documented against the same service boundary
- write semantics, routing, and audit expectations are explicit

## Definition Of Done

This plan is done when future API/MCP implementation can proceed against one explicit shared contract instead of inventing ownership boundaries per slice.

