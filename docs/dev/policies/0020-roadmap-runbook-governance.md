# Policy | Roadmap / Runbook Governance

## Policy

- Keep the roles separate:
  - roadmap: master plan, priority map, and lane catalog
  - runbook: dated turn log of what happened
  - progress ledger: completed-history record
- Treat `ROADMAP.md` as the master plan and revise it cautiously.
- Do not materially reorder, rename, or reprioritize roadmap lanes unless the user explicitly asks for that change, or unless a narrow correction is required to unblock already-requested work.
- Use one canonical top-level roadmap item naming convention, for example `P## | <Lane Title>`, rather than mixing free-form phases, lanes, and milestones.
- If duplicated status text drifts, the roadmap and runbook win over stale summaries elsewhere.
- For any roadmap lane in an active state such as `OPEN`, include a short `Current State` note that says what already exists and what still remains.
- New plan artifacts must live under `docs/dev/plans/` and be wired into both the roadmap and the runbook before they are treated as active.
- For any roadmap lane in an active state such as `OPEN`, require at least one actionable plan unless the lane is being closed in the same slice.
- If a feature does not fit an existing lane, update the roadmap first and make the priority decision explicit.
- Plan wiring and plan-state semantics should be auditable by deterministic helpers rather than relying on chat history or inference.
- After a planning-contract migration for an active repo, record one dated review note or runbook entry that captures the migration, semantic mismatches found, and refinements required.
- Treat progress/history files as retrospective, not planning authority.

## Adoption Notes

Use this module when the repo already carries multiple planning files or has suffered planning drift.
