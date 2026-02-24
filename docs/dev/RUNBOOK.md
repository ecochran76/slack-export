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
- Next: implement Phase A scaffolding (config, schema, CLI skeleton)

## Next Actions Queue

1. Create modular package skeleton
2. Add config loader with env interpolation
3. Add SQLite migrations with workspace-aware schema
4. Introduce CLI command groups for mirror/search/service
5. Add placeholder docs generator/completion entrypoints

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
