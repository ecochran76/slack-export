# Planning Contract Handoff

Date: 2026-04-09
Branch: `feature/planning-contract-migration`

## What Changed

The repo now has a canonical deterministic planning surface at the repo root:

- `ROADMAP.md`
- `RUNBOOK.md`
- `docs/dev/plans/`

The new canonical actionable plan files are:

- `docs/dev/plans/0001-2026-04-09-platform-foundation.md`
- `docs/dev/plans/0002-2026-04-09-installer-upgrade-path.md`
- `docs/dev/plans/0003-2026-04-09-api-mcp-boundary.md`

`AGENTS.md` was also updated to point to the canonical planning surface and the deterministic audit helper.

## Validation

This now passes:

```bash
python /home/ecochran76/workspace.local/agent-skills/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json
```

Expected current result:
- `ok: true`
- roadmap headings match `## P## | Title`
- runbook headings match `## Turn N | YYYY-MM-DD`
- plan files under `docs/dev/plans/` have deterministic filenames, states, lane ids, and wiring

## Important Caveat

Two commits landed on this branch:

- `7272a4b Adopt deterministic planning contract`
- `a5f03f3 Point legacy planning docs to canonical root files`

The first commit is the clean canonical planning migration.

The second commit is not perfectly isolated. `docs/ROADMAP.md` already had substantial uncommitted edits in this workspace before the deprecation-pointer pass, so that commit bundled:

- the intended legacy redirect note
- pre-existing edits in `docs/ROADMAP.md`

Do not assume `a5f03f3` is a clean one-line deprecation patch.

## What Is Canonical Now

For new planning work, use:

- root `ROADMAP.md` as the master plan
- root `RUNBOOK.md` as the dated turn log
- `docs/dev/plans/` for actionable plans

Treat these as legacy/supporting context only:

- `docs/ROADMAP.md`
- `docs/dev/RUNBOOK.md`
- older `docs/dev/*.md` planning notes outside `docs/dev/plans/`

## Recommended Next Step

Review:

```bash
git show 7272a4b
git show a5f03f3 -- docs/ROADMAP.md docs/dev/RUNBOOK.md
```

If the bundled `docs/ROADMAP.md` changes in `a5f03f3` are acceptable, keep this branch as the planning-contract migration branch of record.

If not, open a bounded cleanup branch and separate:

1. legacy redirect notes
2. unrelated `docs/ROADMAP.md` content changes

## What Not To Do

- Do not reopen planning work in legacy `docs/dev/PLAN.md`
- Do not add new active plans outside `docs/dev/plans/`
- Do not treat `docs/ROADMAP.md` or `docs/dev/RUNBOOK.md` as the active planning source of truth anymore
