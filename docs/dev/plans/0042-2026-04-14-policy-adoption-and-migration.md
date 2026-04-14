State: CLOSED
Date: 2026-04-14
Owner: Codex
Roadmap: P01

# 0042 - Policy Adoption And Migration

## Why

The repo had mature local governance in `AGENTS.md`, but it had not yet adopted the shared policy shape under `docs/dev/policies/`. That meant future agents were not instructed to load durable repo-local policy from canonical policy files, and policy compliance depended on one large inline `AGENTS.md` body.

## Current State

Already shipped before this slice:
- canonical roadmap, runbook, and plan surfaces
- planning-contract audit coverage
- repo-local governance in `AGENTS.md`

Remaining gap before this slice:
- no canonical `docs/dev/policies/` directory
- no explicit policy-loading contract telling agents to read repo-local policy files
- adopted bundle was missing the stricter roadmap/runbook governance companion module even though this repo uses canonical roadmap/runbook planning

## Scope

- adopt shared durable policy under `docs/dev/policies/`
- rewire `AGENTS.md` so it explicitly loads repo-local policy from that directory
- preserve repo-specific startup, scope, safety, and architecture nuance in `AGENTS.md`
- add the roadmap/runbook governance companion policy file required by this repo's planning model

## Non-Goals

- reprioritizing roadmap lanes
- deleting legacy planning redirect files
- rewriting published git history
- changing product architecture or operator contracts

## Acceptance Criteria

- `docs/dev/policies/` exists and contains the adopted durable policy set
- `AGENTS.md` explicitly tells agents to read relevant policy files for non-trivial turns
- roadmap/runbook governance is represented in the adopted policy set, not only in inline `AGENTS.md` prose
- roadmap and runbook both record the adoption slice

## Validation

- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/manage_policy.py --repo-root /home/ecochran76/workspace.local/slack-export adopt --json`
- `git status --short`
