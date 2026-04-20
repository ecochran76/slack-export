# MCP Operator Usability Guide

State: CLOSED
Roadmap: P11
Opened: 2026-04-20
Closed: 2026-04-20

## Scope

Make the shipped MCP interface legible as a first-release operator surface.

This slice covers:

- documenting the supported MCP release-baseline tool groups
- documenting the release preflight gates operators should trust before adding agent clients
- documenting outbound-send and listener-delivery expectations
- documenting MCP tracing and machine-readable error behavior
- aligning README, install guidance, roadmap, and runbook references

This slice does not include:

- adding new MCP tools
- changing the MCP protocol or service behavior
- moving tenant onboarding, browser auth, or report CRUD into MCP
- widening default semantic-search policy before the first stable user-scoped release

## Current State

- the repo already exposes MCP over the managed `slack-mirror-mcp` wrapper
- the MCP server can negotiate supported protocol versions and can trace handshake and tool-call dispatch
- `user-env status`, `user-env check-live`, and `release check --require-managed-runtime` now validate real stdio MCP health and bounded concurrent wrapper launches
- the MCP tool surface already includes runtime health, latest runtime report, workspace status, corpus search, search readiness, semantic readiness, outbound sends, thread replies, listener registration, listener status, delivery listing, and delivery acknowledgement
- the missing release piece was operator guidance that states which of those tools are supported baseline behavior and which adjacent workflows remain CLI/API/browser-only

## Outcome

- `docs/API_MCP_CONTRACT.md` now has a dedicated release-baseline section for MCP operators
- the contract doc groups MCP tools by operator task instead of only listing route semantics elsewhere
- the docs state the preflight sequence for managed MCP usage:
  - `slack-mirror-user user-env status --json`
  - `slack-mirror-user user-env check-live --json`
  - `slack-mirror release check --require-managed-runtime --json`
- the docs state the first-release MCP non-goals:
  - tenant onboarding and credential installation remain CLI/browser workflows
  - frontend auth/session management remains API/browser-only
  - named runtime-report and export CRUD remain API/browser workflows
  - heavy semantic rollout/backfill remains explicit CLI/operator work
- README and user-install docs now point operators at the MCP contract before configuring multiple agent clients

## Validation

- `uv run python -m unittest tests.test_mcp_server -v`
- `uv run slack-mirror release check --require-managed-runtime --json`
- `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
