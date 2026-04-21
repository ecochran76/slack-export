# 0093 | Browser Selected Result Report Creation

State: CLOSED

Roadmap: P10

## Current State

- Search results expose stable `action_target` metadata through CLI, API, MCP, and browser-backed JSON endpoints.
- Managed `selected-results` bundles can be created through CLI, API, and MCP.
- Selected-result bundles now render useful human-readable HTML reports at `/exports/{export_id}`.
- Browser users can now select search results with `action_target` metadata and create managed selected-result reports directly from the authenticated `/search` page.

## Scope

- Add browser-side result selection controls to the existing authenticated `/search` page.
- Maintain an in-page selected-result tray based on result `action_target` values.
- Create managed `selected-results` reports through the existing protected `POST /v1/exports` endpoint.
- Link directly to the created report when creation succeeds.

## Non-Goals

- Do not replace the Python-rendered frontend with the future reusable frontend stack.
- Do not add persistent saved selections across browser sessions.
- Do not add DOCX/PDF rendering, bulk result manipulation, or cross-repo shared UI packages.
- Do not change search ranking, query grammar, context-pack expansion, or export manifest schemas.

## Acceptance Criteria

- Browser search results with `action_target` metadata can be selected and unselected.
- The page shows selected count, can clear selections, and can create a selected-result report.
- Report creation sends `kind=selected-results`, selected targets, context-window settings, text-inclusion setting, and title to `/v1/exports`.
- Tests cover the rendered browser controls and protected API payload flow.
- README, API/MCP contract docs, roadmap, and runbook reflect the browser workflow.

## Definition Of Done

- Relevant targeted tests pass.
- Generated docs are refreshed if CLI output/help changes.
- `git diff --check` passes.
- Planning contract audit passes.

## Completion Notes

- Added result-card selection controls for rows that expose stable `action_target` metadata.
- Added an in-page selected-result tray with selected count, clear action, title, before/after context-window controls, and text-inclusion control.
- Wired report creation to protected `POST /v1/exports` with `kind=selected-results`, selected targets, context settings, and title.
- Successful browser-created reports link directly to the managed export viewer.
- Updated README, API/MCP contract docs, roadmap, runbook, and authenticated search-page tests.
