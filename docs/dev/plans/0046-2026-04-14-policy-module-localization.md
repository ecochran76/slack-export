Status: CLOSED
Date: 2026-04-14
Roadmap: P01

# 0046 - Policy Module Localization

## Context

After thinning `AGENTS.md`, the remaining retained policy modules were the real durable contract for this repo. Two of them, `0002-policy-upgrade-management.md` and `0003-policy-adoption-feedback-loop.md`, were still written in generic library terms that referred to release channels, pinned bundles, notes directories, and harvest flows that this repo does not actually use.

## Current State

- the retained policy set is stable and fit-trimmed
- `AGENTS.md` now acts as a thin repo-local routing surface
- `0002` and `0003` still describe a more generic shared-policy workflow than this repo follows

## Goals

- localize the retained policy-upgrade and policy-feedback modules to this repo's actual workflow
- make the expected durable artifacts explicit: bounded plans plus matching runbook entries
- remove references to policy-storage patterns this repo does not use

## Non-Goals

- changing the retained module list
- reopening the broader policy-adoption migration
- adding separate notes or memories directories

## Acceptance Criteria

- `0002-policy-upgrade-management.md` describes this repo's actual upgrade trigger and recording workflow
- `0003-policy-adoption-feedback-loop.md` describes this repo's actual feedback artifact model
- planning governance remains valid after the localization

## Validation

- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git status --short`
