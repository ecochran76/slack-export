# AGENTS.md

Agent operating rules for the `slack-export` repository.

## Session Start

Before substantial work:

1. Read `README.md`.
2. Read the canonical planning files when the task is large enough to need planning:
   - `ROADMAP.md`
   - `RUNBOOK.md`
   - `docs/dev/plans/`
3. Check `git status --short`.
4. For any non-trivial turn, read the relevant entries under `docs/dev/policies/` before implementation.

Do not assume any repo-local `SOUL.md`, `USER.md`, `MEMORY.md`, or `memory/` files exist or are relevant here. Those were mistakenly introduced from a different workspace model and are not part of this repo's operating contract.

## Scope

- `AGENTS.md` includes repo-local guidance plus the policy entry section.
- The durable policy body lives under `docs/dev/policies/`.
- Keep repo-specific commands, environment details, and operational caveats in this file or adjacent local docs.

## Planning Source Of Truth

- Canonical master plan: `ROADMAP.md`
- Canonical runbook: `RUNBOOK.md`
- Canonical actionable plans directory: `docs/dev/plans/`

Repo-specific planning notes:

- For this repo, each `OPEN` plan should say what baseline is already shipped and what work remains. Prefer an explicit `Current State` section over vague status prose.
- Keep `ROADMAP.md` compact enough to function as a priority map. For closed lanes, summarize shipped baseline and grouped child-plan coverage rather than replaying every micro-slice in prose.
- Keep dense implementation archaeology in `docs/dev/plans/` and `RUNBOOK.md`, not inline in the roadmap body.
- Keep `RUNBOOK.md` turn headings unique and monotonic in file order. If numbering drifts, repair the affected heading sequence in the same slice that discovers it.
- Planning wiring should remain auditable with:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Architecture Guardrails

- `slack_mirror` is the canonical owner of DB schema, migrations, sync state, event processing, and search/indexing behavior.
- Keep CLI, API, and MCP surfaces thin over shared application logic.
- Prefer one clear ownership path per concern:
  - ingest and reconcile in `slack_mirror.sync`
  - runtime behavior and listener dispatch in `slack_mirror.service`
  - persistence in `slack_mirror.core`
  - operator entrypoints in `slack_mirror.cli`

## Documentation Change Control

- If a change affects architecture, data flow, or operator workflow, update `README.md` in the same slice.
- If a change affects service setup, background jobs, or deployment behavior, update the relevant docs in `docs/`.
- If implementation changes introduce a new operator contract, command workflow, or service mode, document it.

## Git Hygiene

- Use clear, scoped commit messages.
- Prefer conventional scoped subjects such as `feat(frontend): ...` or `docs(planning): ...` for new commits.

## Parallel Work Policy

Default lanes for this repo when they fit:

- live ops: systemd units, daemon state, queue health, logs, service topology
- ingest and event flow: `slack_mirror.service`, `slack_mirror.sync`, webhook or socket-mode behavior
- persistence and search: `slack_mirror.core`, migrations, FTS, embeddings, query behavior
- CLI and docs: `slack_mirror.cli`, `README.md`, `docs/`, operator-facing command surfaces

## Validation And Handoff

- Validation and handoff policy lives in `docs/dev/policies/0018-validation-and-handoff.md`.

## Turn Closeout

- Turn closeout policy lives in `docs/dev/policies/0014-turn-closeout.md`.

## Policy Evolution

- Keep repo policy changes narrow, justified by observed repo usage, and recorded in `RUNBOOK.md`.
- If a policy change affects planning semantics or audit expectations, update the repo docs and the active plans in the same slice.

## Safety

- Do not exfiltrate secrets or private data.
- Do not run destructive commands without explicit approval.
- Prefer recoverable deletion mechanisms over permanent deletion when cleanup is required.

## Policy Loading Contract

- `AGENTS.md` is a routing surface, not a one-time pointer.
- Re-read the relevant policy files under `docs/dev/policies/` at the start of any non-trivial turn.
- Re-read the relevant policy files when task scope changes mid-session.
- Prefer re-reading policy over improvising from stale assumptions.

## Policy Entry

This repo keeps its durable repo-local policy under `docs/dev/policies/`.

Read and follow:
- `docs/dev/policies/0001-policy-management.md`
- `docs/dev/policies/0002-policy-upgrade-management.md`
- `docs/dev/policies/0003-policy-adoption-feedback-loop.md`
- `docs/dev/policies/0005-planning-discipline.md`
- `docs/dev/policies/0006-parallel-plan-design.md`
- `docs/dev/policies/0007-git-worktree-hygiene.md`
- `docs/dev/policies/0008-commit-history-discipline.md`
- `docs/dev/policies/0009-branch-and-integration-strategy.md`
- `docs/dev/policies/0014-turn-closeout.md`
- `docs/dev/policies/0016-architecture-guardrails.md`
- `docs/dev/policies/0017-documentation-change-control.md`
- `docs/dev/policies/0018-validation-and-handoff.md`
- `docs/dev/policies/0020-roadmap-runbook-governance.md`
