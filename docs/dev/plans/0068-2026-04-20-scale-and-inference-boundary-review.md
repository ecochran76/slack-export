# Scale And Inference Boundary Review

State: CLOSED
Roadmap: P10
Opened: 2026-04-20
Closed: 2026-04-20

## Current State

- `0067` shipped stable `action_target` metadata for corpus results.
- The repo now has named retrieval profiles, rollout diagnostics, fusion diagnostics, and additive action metadata.
- The remaining architectural risk is whether local semantic retrieval can stay SQLite/exact and in-process for the first MCP-capable release, or whether a vector index and long-lived inference process must be introduced immediately.
- The current default profile remains `baseline`, which is intentionally lightweight and safe to time without loading a large model.

## Scope

- Add a bounded operator diagnostic that reports corpus size, embedding/chunk coverage, and timed corpus-search runs by retrieval profile.
- Keep the command read-only and default it to the safe `baseline` profile.
- Record the first measured decision about index backend and model lifecycle boundary.
- Use the evidence to close the Phase 7 decision in the broader local semantic retrieval architecture plan.

## Non-Goals

- Do not add a vector database.
- Do not add a SQLite vector extension.
- Do not change default retrieval behavior.
- Do not make `BAAI/bge-m3` or learned reranking default.
- Do not add a long-lived inference service in this slice.

## Implementation Plan

- Add a shared-service `search_scale_review` method that gathers workspace corpus counts and runs repeated corpus searches through selected retrieval profiles.
- Add a `slack-mirror search scale-review` CLI command with JSON and concise human output.
- Document the command as the decision gate before changing index or inference architecture.
- Run the command against the managed `default` workspace with `baseline` only.

## Acceptance Criteria

- `search scale-review` reports message counts, embedding rows by model, derived-text counts, derived-text chunk counts, chunk embedding rows by model, per-profile latency summaries, and a machine-readable decision payload.
- The default command path does not load heavy local semantic models.
- The first live baseline run records whether the current release should stay SQLite/exact and in-process for baseline retrieval.
- Tests cover the service payload and CLI parser.

## Definition Of Done

- Code, docs, roadmap, and runbook are updated.
- Generated CLI docs are regenerated and checked.
- Targeted tests pass.
- A live managed-DB baseline scale review is run and summarized.
- Planning audit passes.

## Closeout

- Added `SlackMirrorAppService.search_scale_review`.
- Added `slack-mirror search scale-review`.
- Added service and CLI parser tests.
- Documented the command in `README.md`, `docs/CONFIG.md`, and generated CLI reference.
- Live managed-DB baseline run:
  - workspace: `default`
  - messages: `91,556`
  - `local-hash-128` message embeddings: `91,556`
  - derived-text chunks: `0`
  - query: `incident review`
  - repeats: `2`
  - limit: `5`
  - latency: `avg=1821 ms`, `p95=2161 ms`
- Decision:
  - evaluate a SQLite-native vector extension before considering a vector DB or ANN service
  - keep baseline inference in process
  - avoid heavy model lifecycle ownership in individual CLI/API/MCP clients
