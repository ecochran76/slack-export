# 0095 | Selected Result Report Polish

State: CLOSED

Roadmap: P10

## Current State

- Managed `selected-results` bundles preserve a neutral `selected-results.json` artifact.
- Browser, CLI, API, and MCP can create selected-result bundles.
- The generated `index.html` report renders selected items, context, linked messages, and omitted-text states.
- The generated `index.html` report now includes a sticky summary/action header, per-item copy actions, anchors, collapsible context sections, explicit state chips, and print-friendly styling.

## Scope

- Improve the generated selected-result `index.html` report for scanability and operator review.
- Add a sticky summary/action header with selected, resolved, unresolved, generated, and text-policy signals.
- Add per-item status/type chips and copy affordances for target JSON and item permalinks.
- Make context sections collapsible while keeping selected/hit context visible by default.
- Add print-friendly CSS for browser save-to-PDF.
- Cover the rendered HTML contract in tests and update docs/planning.

## Non-Goals

- Do not change `selected-results.json` schema.
- Do not add native DOCX/PDF generation.
- Do not add new API/MCP endpoints.
- Do not migrate report rendering into the future shared frontend stack.

## Acceptance Criteria

- Reports include a scannable summary header and print action.
- Each selected item exposes stable anchors, status/type chips, target JSON copy, and item permalink copy.
- Context and linked-message sections can collapse without hiding the selected item identity.
- Omitted-text and unresolved states remain explicit.
- Existing report content tests pass with new assertions for polish markers.

## Definition Of Done

- Relevant targeted tests pass.
- `git diff --check` passes.
- Planning contract audit passes.

## Completion Notes

- Added a sticky report toolbar with summary counts, print/save-to-PDF action, and report-link copy action.
- Added per-item stable anchors, permalink links, target JSON copy buttons, and status/type chips.
- Wrapped message context, chunk context, and linked Slack messages in collapsible sections.
- Added print CSS that suppresses copy controls and keeps report cards readable for browser save-to-PDF.
- Updated README, API/MCP contract docs, roadmap, runbook, and report-renderer tests.
