# Policy | Planning Discipline

## Policy

- Use bounded plan artifacts under `docs/dev/plans/` or an equivalent plans directory, not ad hoc note files scattered through the repo.
- Plan filenames should use a deterministic serial-plus-date prefix such as `0001-YYYY-MM-DD-plan-slug.md`.
- If the repo uses a canonical long-range plan such as `ROADMAP.md`, treat it as the source of truth for priority.
- If the repo uses a canonical live execution log such as `RUNBOOK.md`, treat it as the source of truth for what happened turn by turn.
- When `RUNBOOK.md` is present, maintain it as a dated turn log with deterministic headings such as `Turn N | YYYY-MM-DD`.
- Treat planning migration for active repos as two phases:
  - structural migration to establish canonical files, naming, and wiring
  - semantic reconciliation to align plan text and lane status with the actual shipped state
- Each plan should carry an explicit deterministic state from a small fixed vocabulary, for example:
  - `PLANNED`
  - `OPEN`
  - `CLOSED`
  - `CANCELLED`
- For any plan in an active state such as `OPEN`, require a short `Current State` section that says what already exists and what still remains.
- Use bounded plan artifacts with explicit scope, non-goals, acceptance criteria, and definition of done.
- When a task is large enough to plan, explicitly separate:
  - parallelizable low-conflict tracks
  - critical-path serialized work
- Keep one critical-path owner visible even when subagents or parallel workers are used.
- Do not let one plan artifact accumulate endless follow-on polish; close it or open a new bounded slice.
- If the repo adopts roadmap/runbook governance, keep plan wiring and plan state aligned with those canonical files.
- When the planning contract changes in a way that affects validation, update the deterministic audit helper in the same slice.
## Adoption Notes

Use this module when the repo has:
- multiple active lanes
- bounded plan artifacts or equivalent planning discipline

Use `roadmap-runbook-governance` as the stricter companion module when the repo keeps canonical `ROADMAP.md` and `RUNBOOK.md` authority.
