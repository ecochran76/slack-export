# 0091 | Selected Result Export Artifacts

State: CLOSED

Roadmap: P10

## Current State

- Corpus search results now expose stable `action_target` values for message and derived-text hits.
- CLI, API, and MCP can expand selected targets into bounded context packs.
- Managed export bundles already exist for channel/day exports, with manifest generation and local/external URL semantics.
- Selected search results cannot yet be persisted as a managed export artifact for later reporting or agent handoff.

## Scope

- Add a managed selected-result export kind that persists a context pack as a neutral JSON bundle artifact.
- Reuse the existing context-pack builder as the only owner of selected-result context expansion.
- Expose the export through the shared service boundary and thin API/CLI/MCP wrappers where appropriate.
- Extend export manifest metadata enough that selected-result bundles are distinguishable from channel/day bundles.

## Non-Goals

- Do not implement rich report rendering, DOCX/PDF generation, or browser-native selected-result manipulation in this slice.
- Do not change search ranking, retrieval profiles, or benchmark semantics.
- Do not extract shared cross-repo frontend/report packages yet.

## Acceptance Criteria

- A caller can submit selected `action_target` values and receive a managed export manifest.
- The export bundle contains a neutral `selected-results.json` artifact with the generated context pack.
- Existing export listing/manifest paths can describe the new bundle kind without channel/day assumptions.
- CLI/API/MCP tests cover the new selected-result export path.
- README, API/MCP contract docs, roadmap, and runbook reflect the operator contract.

## Definition Of Done

- Relevant targeted tests pass.
- Generated CLI docs are refreshed if CLI surface changes.
- `git diff --check` passes.
- Planning contract audit passes.

## Completion Notes

- Added a shared `create_selected_result_export` service method that persists selected `action_target` values as a managed `selected-results` export bundle.
- The bundle contains `selected-results.json`, a minimal `index.html` landing page, and a schema-versioned `manifest.json`.
- `POST /v1/exports`, `slack-mirror search context-pack --managed-export`, and MCP `search.context_export` now expose the same selected-result export contract.
- Export metadata and manifests now distinguish selected-result bundles and report item, resolved, and unresolved counts without channel/day assumptions.
