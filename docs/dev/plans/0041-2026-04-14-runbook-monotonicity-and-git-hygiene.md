State: CLOSED
Date: 2026-04-14
Owner: Codex
Roadmap: P01

# 0041 - Runbook Monotonicity And Git Hygiene

## Why

The prior planning cleanup removed duplicate runbook headings, but it preserved a non-monotonic turn jump that still made the runbook awkward to audit as a dated execution log. The repo policy also asked for scoped commit messages without giving future slices a stronger preferred shape.

## Current State

Already shipped before this slice:
- deterministic planning files and plan wiring
- compact closed-lane roadmap summaries
- globally unique runbook turn headings

Remaining gap before this slice:
- `RUNBOOK.md` headings are unique but not monotonic in file order
- commit-message guidance does not yet state the preferred scoped subject style explicitly

## Scope

- renumber `RUNBOOK.md` turn headings into monotonic file order
- tighten `AGENTS.md` to require monotonic runbook headings
- clarify the preferred scoped commit-subject style for future commits
- wire this narrow governance repair through roadmap and runbook

## Non-Goals

- rewriting published git history
- changing roadmap priorities
- altering product architecture or operator contracts

## Acceptance Criteria

- `RUNBOOK.md` headings are unique and monotonic in file order
- `AGENTS.md` explicitly requires monotonic runbook numbering
- `AGENTS.md` explicitly prefers conventional scoped commit subjects for future commits
- roadmap and runbook both record this narrow governance repair

## Validation

- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git status --short`
