# 0090 | Selected Result Context Packs

State: CLOSED

Roadmap: P10

## Current State

- `0067` added stable `action_target` metadata for corpus search rows.
- `0083` established the cross-corpus direction: selected search results should move toward provider-neutral export/report inputs that can later align with `../imcli` and `../ragmail`.
- Search results are now selectable, but clients still need to manually dereference selected messages, attachment text, and context windows before report/export workflows can consume them.
- The existing channel/day export path remains Slack-specific and date/channel bounded; it is not yet a selected-result export workflow.

## Scope

- Add a shared service contract that accepts selected `action_target` objects and returns a bounded context pack.
- Support message targets first with before/after message context in the same conversation.
- Support derived-text targets with chunk context and linked Slack messages when the source is a file attached to messages.
- Expose the same contract through CLI, API, and MCP.
- Keep the response shape provider-neutral enough to inform later `../imcli` and `../ragmail` convergence work while remaining Slack-owned in this repo.

## Non-Goals

- Do not create managed export bundles from selections in this slice.
- Do not render HTML, DOCX, or PDF from selected results in this slice.
- Do not change search ranking, action-target IDs, or retrieval-profile defaults.
- Do not extract a shared package yet.
- Do not build the browser selection UI in this slice.

## Acceptance Criteria

- A caller can pass message and derived-text `action_target` objects and receive a deterministic context-pack JSON response.
- Message context is bounded by explicit before/after counts and does not cross workspace or channel boundaries.
- Derived-text context includes bounded chunk context and file-linked message references when available.
- CLI, API, and MCP expose the same shared service behavior.
- Tests cover service, API, MCP, and CLI parsing/dispatch for the new contract.

## Definition Of Done

- Code, docs, roadmap, runbook, and tests are updated.
- Targeted service/API/MCP/CLI tests pass.
- Generated docs are refreshed if CLI help changes.
- Planning audit and `git diff --check` pass.

## Closure Notes

- Added shared `build_search_context_pack` service logic for selected message and derived-text action targets.
- Message targets now resolve to bounded before/hit/after context without crossing workspace or channel boundaries.
- Derived-text targets now resolve to bounded chunk context and linked Slack messages when the source is a file attached to messages.
- Added CLI, API, and MCP surfaces for the same context-pack contract.
- This intentionally stops before managed export/report rendering; the output is the handoff artifact for a later selected-result export/report slice.
