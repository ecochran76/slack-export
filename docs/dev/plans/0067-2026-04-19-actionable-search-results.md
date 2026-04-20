# 0067 | Actionable Search Results

State: OPEN

Roadmap: P10

## Current State

- `0066` added explicit corpus fusion controls and stable `_explain` metadata.
- Corpus results carry enough ranking context for clients to understand why a result appeared.
- Search results are still passive rows: CLI, API, MCP, and browser clients do not yet get a stable action target contract.
- Export/report workflows still require callers to translate search rows into message, file, canvas, chunk, or thread identifiers themselves.

## Scope

- Define stable action-target metadata for corpus search results.
- Add a shared result-selection contract that can be used by CLI, API, MCP, and later frontend workflows.
- Preserve current result shapes while adding additive metadata.
- Support message and derived-text targets first, with room for thread, file, canvas, and chunk targets.
- Document how selected candidates should flow into export/report/action workflows.

## Non-Goals

- Do not build the frontend selection UI in this slice.
- Do not implement bulk export/report creation from selections in this slice.
- Do not change search ranking defaults.
- Do not introduce a new search index or storage backend.

## Acceptance Criteria

- Corpus result rows include stable action-target metadata for message and derived-text results.
- API and MCP clients can round-trip selected result candidates without re-parsing display fields.
- CLI JSON output exposes the same metadata as service/API/MCP output.
- The contract documents target kinds, identifiers, and expected future handoff to export/report workflows.
- Tests cover message and derived-text action targets.

## Definition Of Done

- Code, docs, roadmap, runbook, and tests are updated.
- Targeted search, service, API, MCP, and CLI tests pass.
- Planning audit passes.
