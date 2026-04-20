# 0066 | Query Fusion And Explainability Hardening

State: CLOSED

Roadmap: P10

## Current State

- `0065` shipped profile-aware semantic readiness across CLI, API, MCP, and tenant settings.
- Corpus hybrid search currently uses weighted score fusion only.
- CLI `--explain` prints a few score fields, but API/MCP consumers do not get a stable explain contract.
- The architecture plan calls for deterministic fusion and explainability before actionability and frontend migration work.

## Scope

- Add an explicit corpus hybrid fusion method option.
- Preserve current weighted-score fusion as the default.
- Add reciprocal-rank fusion as an opt-in deterministic strategy.
- Attach stable machine-readable explain metadata to corpus results.
- Thread the new option through CLI, service, API, and MCP without changing existing search defaults.

## Non-Goals

- Do not change the default retrieval profile.
- Do not promote `local-bge` or learned reranking.
- Do not implement selectable/actionable search results.
- Do not introduce a vector database or ANN index.

## Acceptance Criteria

- Corpus hybrid search supports `weighted` and `rrf` fusion.
- Existing callers keep weighted behavior unless they explicitly request `rrf`.
- Search results include an `_explain` object with source, fusion method, rank positions, raw scores, weights, and final score.
- CLI, API, and MCP can pass the fusion method consistently.
- Tests cover weighted explain metadata and RRF ranking behavior.

## Definition Of Done

- Code, docs, generated CLI reference, roadmap, runbook, and tests are updated.
- Targeted search, CLI, API, MCP, and service tests pass.
- Planning audit passes.

## Closure Notes

- Ran a bounded baseline catch-up for `default`; after embedding 8 newly ingested messages, baseline readiness reported `91543/91543`.
- Added corpus `fusion_method` support with `weighted` as the default and `rrf` as opt-in.
- Threaded `fusion` through CLI, API, MCP, and the shared service boundary.
- Added `_explain` metadata to corpus results for source, fusion method, scores, ranks, weights, and rerank provider.
- Preserved existing weighted behavior for existing callers.
