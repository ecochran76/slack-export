# Policy | Policy Adoption Feedback Loop

## Policy

- After first policy adoption, major policy upgrade, or meaningful policy friction, record a dated feedback artifact in the adopting repo.
- The feedback note should identify at least:
  - the policy source reviewed
  - modules adopted
  - modules deferred, retired, or overridden locally
  - what worked cleanly
  - what created friction or ambiguity
  - what should remain repo-local
  - what may warrant an upstream module, profile, or selector change
- For this repo, store policy-adoption and policy-fit feedback in a dated plan plus matching `RUNBOOK.md` entry; do not require separate `docs/dev/notes/` or `docs/dev/memories/` directories.
- Do not leave important adoption lessons only in chat history, commit messages, or oral maintainer knowledge.
- When feedback appears reusable across repos, capture that in the dated plan or runbook entry so it can be normalized upstream later instead of being lost.
- When a repo adopts local overrides instead of the exact starter profile, record why; those reasons are often the best signal for future shared policy refinement.
- When the repo upgrades policy, compare the new experience to prior adoption and trim slices so repeated friction becomes visible over time.
- For this repo, the existing policy-governance slices under `docs/dev/plans/0042`, `0044`, and later follow-ups are valid feedback artifacts when they clearly capture the decision and resulting fit.
## Adoption Notes

Use this module when repos adopt shared policy from an external source library and want a durable loop between downstream adoption experience and upstream policy improvement.
