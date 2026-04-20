# Release Profile And Semantic Search Policy

State: CLOSED
Roadmap: P10
Opened: 2026-04-20
Closed: 2026-04-20

## Current State

- `0068` closed the scale and inference-boundary review with a repeatable `search scale-review` diagnostic.
- The managed `default` baseline review measured `p95=2161 ms` over repeated baseline hybrid corpus search on `91,556` messages.
- The current code supports named retrieval profiles, rollout planning, semantic readiness, fusion diagnostics, explain metadata, result action targets, and scale review.
- The remaining risk for the first MCP-capable release is not missing feature plumbing; it is over-promoting experimental semantic search behavior before the install, MCP, and multi-client operator experience are stable.

## Scope

- Lock release-safe default search behavior for the first stable MCP-capable user-scoped release.
- Record which semantic features are supported, opt-in, experimental, or deferred.
- Sideline DuckDB for the present release path.
- Record the next evidence-backed performance evaluation path.
- Update roadmap, architecture plan, operator docs, and runbook.

## Non-Goals

- Do not change runtime defaults.
- Do not add a vector index.
- Do not add DuckDB.
- Do not promote `BAAI/bge-m3` as the default profile.
- Do not promote learned reranking.
- Do not implement a long-lived inference service in this slice.

## Release Policy

- Default installed search profile:
  - `baseline`
  - `local-hash-128`
  - `local_hash`
  - hybrid mode
  - weighted fusion default
  - no reranking by default
- Supported opt-in local semantic profile:
  - `local-bge`
  - `BAAI/bge-m3`
  - `sentence_transformers`
  - explicit operator rollout only
  - must pass provider probe, semantic readiness, rollout plan, bounded backfill, and search health before tenant promotion
- Experimental profile:
  - `local-bge-rerank`
  - `BAAI/bge-reranker-v2-m3`
  - not release default
  - use only for bounded evaluation because live rehearsal did not show enough stable relevance lift to justify rollout
- Deferred:
  - DuckDB as a search backend or canonical store
  - vector DB / ANN service
  - default learned reranking
  - broad BGE rollout without tenant-level readiness evidence

## Next Technical Evaluation

- Evaluate a SQLite-native vector extension before considering a vector DB or ANN service.
- Keep SQLite as the canonical source of truth.
- Treat DuckDB as a possible future analytics/reporting/search-sidecar experiment, not as part of the first MCP-capable release path.
- If heavy local models are promoted later, add a long-lived local inference boundary so individual CLI/API/MCP clients do not independently own model lifecycle.

## Acceptance Criteria

- Release docs distinguish baseline, supported opt-in local semantic, experimental reranking, and deferred architecture work.
- Roadmap no longer leaves `0069` as an open semantic-search slice.
- The broader `0054` architecture plan records the Phase 8 release/default policy.
- Runtime smoke verifies current profile/readiness/scale-review commands still work.
- Planning audit passes.

## Closeout

- Updated release policy in `README.md` and `docs/CONFIG.md`.
- Updated `ROADMAP.md` P10 current state and remaining recommendations.
- Updated `0054` Phase 8 with the release/default policy.
- Recorded DuckDB as sidelined for the current release path.
- Confirmed no runtime defaults changed.
