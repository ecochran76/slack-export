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

Do not assume any repo-local `SOUL.md`, `USER.md`, `MEMORY.md`, or `memory/` files exist or are relevant here. Those were mistakenly introduced from a different workspace model and are not part of this repo's operating contract.

## Scope

This repo is for the Slack mirror platform:

- ingest and reconcile Slack workspaces
- persist canonical mirror state in SQLite
- support keyword and semantic search
- run in supported live-service topologies
- expose shared service logic through CLI, API, and MCP
- support outbound messaging and listener workflows

## Planning Source Of Truth

- Canonical master plan: `ROADMAP.md`
- Canonical runbook: `RUNBOOK.md`
- Canonical actionable plans directory: `docs/dev/plans/`

Rules:

- Treat `ROADMAP.md` as the authoritative priority map.
- Treat `RUNBOOK.md` as the dated execution log.
- Keep the roles separate:
  - roadmap: priority map and lane catalog
  - runbook: dated turn log of what happened
- Revise `ROADMAP.md` cautiously.
- Do not materially reorder, rename, or reprioritize roadmap lanes unless the user explicitly asks for that change or a narrow correction is required to reflect already-requested work.
- Any actionable plan should live under `docs/dev/plans/`.
- Use deterministic filenames like `0001-2026-04-09-plan-slug.md`.
- Use deterministic states such as `PLANNED`, `OPEN`, `CLOSED`, or `CANCELLED`.
- New plan files are not active until they are wired into both `ROADMAP.md` and `RUNBOOK.md`.
- Keep completed plans and migration notes visible; mark them complete or superseded instead of deleting them.
- For this repo, each `OPEN` plan should say what baseline is already shipped and what work remains. Prefer an explicit `Current State` section over vague status prose.
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
- Do not add a second canonical database, shadow index, or parallel service topology without documenting the split.
- Do not preserve accidental duplication when a smaller shared slice would do.

## Documentation Change Control

- If a change affects architecture, data flow, or operator workflow, update `README.md` in the same slice.
- If a change affects service setup, background jobs, or deployment behavior, update the relevant docs in `docs/`.
- If implementation changes introduce a new operator contract, command workflow, or service mode, document it.
- Keep planning docs, service files, and implementation aligned.
- Do not rely on chat history as the authoritative explanation of why a change happened; record the reason in the repo docs or runbook.

## Git Hygiene

- Check `git status --short` before starting and before finishing substantial work.
- Treat pre-existing dirty state as a real constraint, not background noise.
- Keep changes small and coherent.
- Do not mix unrelated refactors with the task at hand.
- Prefer one bounded branch or execution slice per roadmap lane or feature slice.
- If overlapping dirty work exists, open a reconciliation step instead of pretending the merge boundary is clean.
- Run relevant validation before closing out work.
- Use clear, scoped commit messages.
- Do not amend, force-push, or rewrite published history unless explicitly requested.

## Parallel Work Policy

- When planning substantial work, explicitly look for low-conflict tasks that can be delegated or run in parallel.
- Good candidates:
  - read-only investigation of different subsystems
  - implementation in one area while validation runs elsewhere
  - ops inspection or service verification alongside local code work
  - independent edits with disjoint write scopes
- Do not parallelize tightly coupled edits to the same files, schema, or control flow unless coordination is explicit.
- Assign clear ownership for each parallel slice.
- Merge and verify parallel work before declaring the task complete.

Default lanes for this repo when they fit:

- live ops: systemd units, daemon state, queue health, logs, service topology
- ingest and event flow: `slack_mirror.service`, `slack_mirror.sync`, webhook or socket-mode behavior
- persistence and search: `slack_mirror.core`, migrations, FTS, embeddings, query behavior
- CLI and docs: `slack_mirror.cli`, `README.md`, `docs/`, operator-facing command surfaces

## Validation And Handoff

- Run relevant validation for the touched surface before commit, merge prep, or handoff.
- Prefer targeted validation for narrow changes and broader validation for cross-cutting operator-visible changes.
- Record concrete pass/fail evidence in the closeout note.
- When live or manual smoke matters, say whether it was run and what it proved.
- Keep residual risk explicit and small.

## Turn Closeout

- End substantial turns with a best recommendation or next slice, not a vague request for direction when a clear next move exists.
- Use explicit alternate closeout modes only when the task genuinely ends in:
  - audit findings
  - a bounded plan
  - a pause for review or priority choice

## Policy Evolution

- This repo's policy may be refined when real execution exposes ambiguity, drift, or missing controls.
- Keep policy changes narrow, justified by observed repo usage, and recorded in `RUNBOOK.md`.
- If a policy change affects planning semantics or audit expectations, update the repo docs and the active plans in the same slice.
- Prefer extending shared policy concepts over inventing repo-local taxonomy churn.
- When a rule seems reusable across repos, leave a harvest note or normalize it back into `/home/ecochran76/workspace.local/agent-policies` instead of trapping it here.

## Safety

- Do not exfiltrate secrets or private data.
- Do not run destructive commands without explicit approval.
- Prefer recoverable deletion mechanisms over permanent deletion when cleanup is required.
