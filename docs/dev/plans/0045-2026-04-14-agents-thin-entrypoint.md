Status: CLOSED
Date: 2026-04-14
Roadmap: P01

# 0045 - AGENTS Thin Entrypoint

## Context

After policy adoption and fit trimming, `AGENTS.md` was still carrying a large amount of prose that duplicated the retained policy modules under `docs/dev/policies/`. That weakened the value of the policy split by leaving two places that future edits could drift apart.

## Current State

- `docs/dev/policies/` is the canonical durable policy surface
- `AGENTS.md` correctly points agents at that policy surface
- `AGENTS.md` still repeats large portions of planning, git, validation, closeout, and routing policy verbatim

## Goals

- keep `AGENTS.md` as a thin repo-local entrypoint
- retain repo-specific startup, planning nuance, architecture boundaries, documentation commands, and lane hints
- remove duplicated durable policy prose that already lives in retained policy modules

## Non-Goals

- changing the retained policy module set
- changing the roadmap or runbook contract itself
- weakening the requirement that agents read policy files on non-trivial turns

## Acceptance Criteria

- `AGENTS.md` remains explicit about reading repo-local policy files
- repo-specific guidance remains local and easy to find
- duplicated durable policy prose is reduced materially
- planning-contract validation still passes after the trim

## Validation

- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git status --short`
