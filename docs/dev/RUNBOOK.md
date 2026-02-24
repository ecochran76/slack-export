# Runbook (Handoff + Operations)

This file is the continuity guide for future agents and contributors.

## Current Mission

Evolve this repo from one-time exporter to multi-workspace, continuously updated mirror platform.

## Working Conventions

- Planning/dev docs live in `docs/dev/`
- User-facing docs live in `docs/`
- Keep this runbook updated at each meaningful milestone
- Prefer small, coherent commits with explicit milestone labels

## Session Startup Checklist

1. Read:
   - `README.md`
   - `docs/ARCHITECTURE.md`
   - `docs/ROADMAP.md`
   - `docs/dev/PLAN.md`
   - `docs/dev/RUNBOOK.md`
2. Check repo status:
   - `git status --short --branch`
3. Confirm branch and open tasks before coding

## Milestone Log

### 2026-02-23 — Planning docs baseline

- Captured architecture, roadmap, engineering plan, and runbook
- Established docs split (`docs/` vs `docs/dev/`)

### 2026-02-23 — Phase A scaffolding (initial)

- Added `config.example.yaml` with env-var interpolation patterns
- Added `slack_mirror` package skeleton (`core`, `cli`, `search`, `service`, `integrations`)
- Added SQLite migration scaffold: `slack_mirror/core/migrations/0001_init.sql`
- Added config loader with `${ENV}` / `${ENV:-default}` support
- Added DB connector + migration applier
- Added CLI skeleton (`slack-mirror`) with stubs for:
  - `mirror init`
  - `workspaces list`
  - `channels sync-from-tool`
  - `docs generate`
  - `completion print bash|zsh`
- Added adapter for existing `~/.openclaw/workspace/scripts/slack_channels`

## Next Actions Queue

1. Wire CLI entrypoint via packaging (`pyproject.toml` script)
2. Add unit tests for config interpolation + migrations
3. Implement `workspaces add/verify` + workspace bootstrap into DB
4. Build initial backfill engine (users/channels first)
5. Add user-facing docs for config + quickstart for `slack-mirror`

## Decision Log Pointer

Use `docs/dev/DECISIONS.md` for ADR-style architectural decisions.

## Useful Commands

```bash
# quick sanity
python3 -m py_compile slack_export.py

# repo state
git status --short --branch
git log --oneline -n 10
```

## Handoff Template

When pausing, append:

- What changed
- What is pending
- Risks/blockers
- Recommended next command
