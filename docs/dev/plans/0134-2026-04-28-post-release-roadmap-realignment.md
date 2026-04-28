# 0134 | Post-release roadmap realignment

State: CLOSED

Roadmap: P11

## Purpose

Close the first stable MCP-capable user-scoped release lane after `v0.2.0` and
make the roadmap point back to post-release semantic retrieval work.

## Current State

`v0.2.0` is tagged and pushed. `master` is back on `0.2.1-dev`. `P11` still
contained stale open-lane language that treated the first stable release as the
immediate priority before `P10`.

## Scope

- Mark `P11` closed.
- Replace stale future-tense release-blocker language with the shipped
  `v0.2.0` baseline.
- Keep future release-hardening work scoped to later narrow maintenance plans.
- Update `P10` wording so semantic retrieval work is no longer blocked on the
  first stable MCP release.

## Non-goals

- Do not start new semantic implementation work in this slice.
- Do not alter release tags or package versions.
- Do not close `P10`, `P12`, or frontend/tenant lanes.

## Acceptance

- Roadmap records `P11` as closed.
- Roadmap recommends resuming semantic retrieval diagnostics as the next active
  technical lane.
- Planning audit and `git diff --check` pass.

## Status

CLOSED. The roadmap now treats `v0.2.0` as shipped and routes follow-up work
back toward `P10` semantic retrieval quality.
