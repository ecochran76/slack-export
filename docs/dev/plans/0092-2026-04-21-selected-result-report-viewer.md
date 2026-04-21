# 0092 | Selected Result Report Viewer

State: CLOSED

Roadmap: P10

## Current State

- `0090` added bounded selected-result context packs over corpus `action_target` values.
- `0091` added managed `selected-results` export bundles containing `selected-results.json`, `manifest.json`, and a minimal `index.html` landing page.
- The selected-result bundle is durable but still not ergonomic as a human report because the HTML only links to raw JSON.

## Scope

- Render a useful HTML report in the managed selected-result export `index.html`.
- Use the existing `selected-results.json` payload and context-pack shape as the only source of report data.
- Show selected items, target metadata, resolved/unresolved state, message context, derived-text chunk context, and linked messages where present.
- Keep the renderer local to Slack Mirror while preserving the neutral JSON artifact for future shared report packages.

## Non-Goals

- Do not add browser-side search-result selection controls in this slice.
- Do not add DOCX/PDF rendering for selected-result exports.
- Do not change corpus search ranking, context-pack expansion, or MCP protocol semantics.

## Acceptance Criteria

- A selected-result managed export creates an `index.html` that is useful without opening raw JSON.
- The report remains safe to render for no-text exports and clearly distinguishes omitted text from missing targets.
- Tests cover message and derived-text report rendering from representative context-pack payloads.
- README, API/MCP contract docs, roadmap, and runbook reflect the report-viewer layer.

## Definition Of Done

- Relevant targeted tests pass.
- Generated docs are refreshed if CLI output/help changes.
- `git diff --check` passes.
- Planning contract audit passes.

## Completion Notes

- Replaced the placeholder selected-result export landing page with a report renderer over the existing context-pack payload.
- The report now shows selected item status, target metadata, message context timelines, derived-text chunk context, and linked Slack messages when present.
- No-text exports remain useful because the report renders structure and explicitly marks text as omitted.
- Added tests for message-report rendering and derived-text/no-text report rendering.
