# Outbound Listeners Hardening

State: CLOSED
Roadmap: P05
Opened: 2026-04-09

## Scope

Harden the already-implemented outbound messaging and listener capabilities into a stable platform contract:

- outbound auth and workspace-routing discipline
- DM/user-ref resolution rules
- idempotency and retry expectations
- listener registration, delivery, and acknowledgement contract
- operator validation and documentation

## Current State

- outbound send and thread reply exist through the shared app service
- DM user-ref resolution and idempotency protections exist
- listener registration, delivery listing, and acknowledgement exist through service, API, and MCP
- the shipped transport contract now documents outbound-write semantics plus listener registration, delivery, and acknowledgement behavior in `docs/API_MCP_CONTRACT.md`
- missing listener/delivery IDs now fail explicitly instead of silently succeeding through unregister/ack paths
- the current local queue-delivery model is now treated as the intentional shipped listener contract
- richer retry/requeue policy is deferred unless a concrete subscribed-process requirement appears

## Parallel Tracks

### Track A | Outbound Write Contract

- explicit write-token policy
- target resolution rules
- send and thread-reply audit semantics

### Track B | Listener Contract

- listener registration and filtering rules
- delivery states and acknowledgement semantics
- replay and failure-handling expectations

### Track C | Operator And Surface Wiring

- CLI/API/MCP consistency
- validation and runbook updates
- tests for routing, retries, and ambiguous targets

## Critical Path

- settle the outbound and listener contract first
- then tighten operator validation and surface-specific documentation around that contract

## Non-Goals

- arbitrary remote webhook ecosystems
- unbounded automation features beyond the local listener model
- broad Slack administrative write automation outside messaging and reply workflows

## Acceptance Criteria

- outbound send and reply behavior are documented as supported capabilities
- listener behavior is explicit enough for local consumers to rely on safely
- API, MCP, and operator docs describe the same write and listener contract
- validation coverage exists for the highest-risk routing and idempotency cases

## Definition Of Done

This plan is done when outbound messaging and listener support can be treated as intentional platform features rather than implementation slices that only happen to exist in code.
