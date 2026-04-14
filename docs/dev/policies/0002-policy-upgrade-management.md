# Policy | Policy Upgrade Management

## Policy

- Treat shared policy upgrades as intentional maintenance work, not accidental drift from copying files ad hoc.
- For this repo, treat `/home/ecochran76/workspace.local/agent-policies` and its selector scripts as the authoritative policy-upgrade source unless the local workflow changes.
- Review policy updates when one of these happens:
  - the selector starts recommending a materially different module set
  - the repo adds a workflow the retained policy modules do not cover cleanly
  - repeated local overrides suggest the shared module text no longer fits this repo well
- When upstream policy changes appear, decide explicitly whether to:
  - adopt a new module
  - upgrade an already adopted module
  - retire a no-longer-useful local policy
  - defer the change for a documented reason
- Review profile changes separately from module changes; do not let a broader selector profile silently expand the repo's retained policy set.
- When a local repo has customized policy, prefer merge review over blind overwrite.
- Retire superseded local policy files explicitly when a shared replacement makes them unnecessary.
- Scope any upgrade against the current retained module set first; this repo prefers fit-reviewed policy over full-profile adoption.
- Keep policy upgrade decisions durable in repo docs, bounded plans, and the runbook rather than leaving rationale only in chat or commit history.
- A single dated plan plus matching `RUNBOOK.md` entry may serve as the canonical artifact when it records:
  - what was reviewed
  - what changed or was intentionally left unchanged
  - why the decision fit this repo
  - any follow-up needed
## Adoption Notes

Use this module when the repo depends on an external or shared policy library and needs a durable contract for staying current without adopting every upstream change blindly.
