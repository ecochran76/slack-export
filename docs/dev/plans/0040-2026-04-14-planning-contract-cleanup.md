State: CLOSED
Date: 2026-04-14
Owner: Codex
Roadmap: P01

# 0040 - Planning Contract Cleanup

## Why

The repo planning mechanics are working, but the roadmap has drifted from a priority map into a dense shipped-feature ledger. The runbook also has a duplicate turn number. This slice restores the planning surfaces to the repo policy contract without changing product priorities.

## Current State

Already shipped before this slice:
- deterministic plan filenames and plan wiring
- canonical roadmap and runbook files
- auditable planning-contract validation

Remaining gap before this slice:
- closed lanes, especially `P02`, are too verbose to function as a compact priority map
- the runbook has duplicate `Turn 17` headings
- repo policy does not explicitly prohibit roadmap bloat on closed lanes

## Scope

- compress closed-lane roadmap prose into grouped shipped-baseline summaries
- keep explicit plan wiring intact while reducing roadmap verbosity
- add repo-policy guidance that closed lanes should summarize rather than replay every micro-slice
- repair the duplicate runbook turn heading and record the cleanup in the runbook

## Non-Goals

- reprioritizing roadmap lanes
- deleting historical plans or runbook entries
- changing product architecture or operator contracts

## Acceptance Criteria

- the roadmap remains fully wired to the closed plans but reads as a compact priority map
- closed lanes summarize shipped baseline and point detail readers at plans/runbook
- `AGENTS.md` explicitly guards against roadmap density drift on closed lanes
- the runbook no longer contains duplicate turn headings

## Validation

- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git status --short`
