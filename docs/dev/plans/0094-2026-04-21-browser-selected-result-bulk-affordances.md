# 0094 | Browser Selected Result Bulk Affordances

State: CLOSED

Roadmap: P10

## Current State

- Search result rows expose stable `action_target` metadata.
- Browser users can select individual result rows on authenticated `/search`.
- Browser users can create managed `selected-results` reports from the selected-result tray.
- Browser users can now select all visible selectable results and deselect only currently visible selected results when staging candidates.

## Scope

- Add browser-side bulk selection controls to the existing authenticated `/search` page.
- Support selecting all currently visible selectable results.
- Support deselecting all currently visible selected results without clearing hidden/off-page selections.
- Preserve the existing clear-all action and selected-result report creation flow.
- Cover the rendered controls in tests and update planning/docs.

## Non-Goals

- Do not add persistent saved selections across browser sessions.
- Do not add cross-page server-side selection state.
- Do not add DOCX/PDF rendering or report artifact schema changes.
- Do not move this temporary Python-rendered UI into the future shared frontend stack.

## Acceptance Criteria

- The search page renders visible-result bulk select and deselect controls.
- Selecting visible results uses each result's `action_target` and updates the selected-result tray count.
- Deselecting visible results removes only currently visible results from the tray.
- Existing clear-all and create-report behavior remains unchanged.
- Tests cover the rendered controls and JavaScript contract markers.

## Definition Of Done

- Relevant targeted tests pass.
- `git diff --check` passes.
- Planning contract audit passes.

## Completion Notes

- Added `Select visible` and `Deselect visible` controls to the selected-result tray.
- Bulk selection reads each visible result's serialized `action_target`, updates the selected-target map, and refreshes result-card checked/selected state.
- Deselect visible removes only currently visible results, preserving selections from other pages.
- Existing clear-all and create-report behavior remains unchanged.
- Updated README, API/MCP contract docs, roadmap, runbook, and authenticated search-page tests.
