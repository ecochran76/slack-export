# 0096 | Frontend Selected Result Contract Model

State: CLOSED

Roadmap: P09

## Current State

- `0051` defines the reusable operator-console architecture direction as Vite, React, TypeScript, and neutral shared UI primitives.
- `0083` defines the cross-corpus convergence direction for selected-result export/report contracts across `slack-export`, `../imcli`, and `../ragmail`.
- `0090` through `0095` stabilized Slack Mirror's selected-result workflow:
  - corpus results expose `action_target`
  - context packs expand selected targets
  - managed `selected-results` bundles persist neutral JSON artifacts
  - `/search` can stage selected results and create reports
  - generated reports now expose polished report affordances
- Before this slice, the frontend worktree did not have a repo-local frontend boundary or typed model for representing selected search candidates, selected-result reports, context windows, or managed artifacts.
- The frontend worktree now has a repo-local `frontend/` boundary and TypeScript selected-result contracts that can seed future shared operator UI work.

## Scope

- Add a minimal `frontend/` boundary for reusable operator-console contracts.
- Model selected search candidates, selected-result report artifacts, context windows, managed artifacts, and report UI actions with provider-neutral TypeScript types.
- Document how Slack Mirror fields map into the neutral UI-facing model.
- Keep the model extractable to a future shared communications UI package without creating that package now.
- Update roadmap and runbook wiring.

## Non-Goals

- Do not scaffold the full Vite/React app in this slice.
- Do not replace Python-rendered `/search`, `/settings/tenants`, or `/exports` routes.
- Do not introduce a package build pipeline or npm dependency tree yet.
- Do not change API, MCP, CLI, or `selected-results.json` schemas.
- Do not extract a shared package into a sibling repo yet.

## Acceptance Criteria

- `frontend/` contains provider-neutral selected-result contract types.
- The contract avoids Slack-only nouns in shared type names.
- Documentation explains Slack-to-neutral mapping and the boundary between shared UI types and repo-local adapters.
- P09 roadmap text points to this slice as the contract-first step before app scaffolding.
- Planning audit and diff checks pass.

## Definition Of Done

- Type contract files are present and readable.
- JSON/markdown/frontend contract docs pass lightweight syntax checks where applicable.
- `git diff --check` passes.
- Planning contract audit passes.

## Completion Notes

- Added `frontend/README.md`.
- Added provider-neutral selected-result UI contracts under `frontend/src/contracts/`.
- Added `docs/dev/FRONTEND_CONTRACTS.md` with Slack-to-neutral mapping and adapter-boundary guidance.
- Kept the slice contract-only: no Vite/React app scaffold, package build pipeline, API schema change, or shared-package extraction.
- Validated the TypeScript contracts with local `tsc --noEmit --strict`.
