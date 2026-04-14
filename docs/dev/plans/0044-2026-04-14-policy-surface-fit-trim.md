Status: CLOSED
Date: 2026-04-14
Roadmap: P01

# 0044 - Policy Surface Fit Trim

## Context

The first policy-adoption slice installed the full selector-recommended module set so the repo could move quickly into canonical `docs/dev/policies/` shape. A follow-up fit review showed that several installed modules were broader than this repo's actual operating contract. They described optional continuity, release, fork-maintenance, and agent-orchestration patterns that are not active repo requirements today.

## Current State

- shared durable repo policy is installed under `docs/dev/policies/`
- `AGENTS.md` already routes non-trivial turns through the adopted policy directory
- planning governance and policy adoption are working
- the installed module set is broader than the repo actually needs

## Goals

- keep only the policy modules that match this repo's real operating contract
- remove clearly non-applicable modules from both `docs/dev/policies/` and the `AGENTS.md` policy entry
- record the trim as a dated governance slice so future policy upgrades have a clear baseline

## Non-Goals

- changing product priorities or roadmap lanes
- reworking the planning contract that was just repaired
- adding notes, memories, release automation, or fork-maintenance workflow that the repo does not currently use

## Acceptance Criteria

- `AGENTS.md` points only at the retained policy modules
- non-applicable policy files are removed from `docs/dev/policies/`
- the planning contract remains valid after the trim
- policy adoption checks still pass after the narrower retained set

## Validation

- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/manage_policy.py --repo-root /home/ecochran76/workspace.local/slack-export adopt --json`
