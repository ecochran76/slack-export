State: CLOSED
Date: 2026-04-14
Owner: Codex
Roadmap: P01

# 0043 - Legacy Runbook Retirement

## Why

The repo's canonical runbook had already moved to the root `RUNBOOK.md`, but the retained legacy file `docs/dev/RUNBOOK.md` still looked like a second canonical runbook authority to deterministic policy selectors. That kept policy adoption in a migration-first state even after the durable policy bundle was installed.

## Current State

Already shipped before this slice:
- root `RUNBOOK.md` is the canonical dated execution log
- legacy planning redirects exist for older links and historical context
- shared durable repo policy is adopted under `docs/dev/policies/`

Remaining gap before this slice:
- `docs/dev/RUNBOOK.md` still exists at a canonical-looking path and triggers duplicate-authority detection
- some repo docs still reference that old path directly

## Scope

- retire `docs/dev/RUNBOOK.md` as a canonical-looking path
- preserve the old continuity log under an explicitly legacy location
- update repo references that still point at the old duplicate path
- record the cleanup in roadmap and runbook

## Non-Goals

- deleting the historical continuity log content
- changing the root runbook contract
- reprioritizing roadmap lanes or altering product behavior

## Acceptance Criteria

- root `RUNBOOK.md` is the only canonical runbook authority path in the repo
- the old continuity log remains available under an explicitly legacy location
- deterministic selector adoption no longer reports duplicate canonical runbook authorities
- roadmap and runbook both record this cleanup slice

## Validation

- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/manage_policy.py --repo-root /home/ecochran76/workspace.local/slack-export adopt --json`
- `git status --short`
