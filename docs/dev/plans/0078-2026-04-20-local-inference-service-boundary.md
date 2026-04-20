# Local Inference Service Boundary

State: CLOSED
Roadmap: P10
Opened: 2026-04-20

## Current State

- `0077` made the release `baseline` path interactive for the measured `default` query.
- Managed `local-bge` now has a fast warm query path, but still pays a cold model-load cost around `15.7s` in the measured scale review.
- The embedding provider seam already supports an HTTP provider contract for `embed_texts`.
- The reranker provider seam currently supports heuristic and in-process CrossEncoder providers, but not an HTTP provider.
- The managed user runtime currently installs CLI/API/MCP wrappers and API/runtime-report units, but not a long-lived local inference unit.

## Scope

- Add a loopback-only local inference HTTP server that can:
  - embed text batches through the existing embedding-provider seam
  - score rerank query/document batches through the reranker-provider seam
  - keep loaded model objects warm inside one process
- Add HTTP reranker provider support so `local-bge-rerank` can use the same service boundary as embeddings.
- Add CLI commands to run and probe the inference server.
- Add a managed user-scope wrapper and systemd user unit for the inference service.
- Add tests and docs for the new boundary.

## Non-Goals

- Do not make `local-bge` the default retrieval profile.
- Do not broaden BGE rollout beyond the existing bounded `default` rehearsal.
- Do not add a vector DB, ANN service, or SQLite vector extension.
- Do not expose the inference service on non-loopback interfaces.
- Do not require the inference service for the release `baseline` profile.

## Tracks

- Critical path:
  - plan/roadmap/runbook wiring
  - local inference HTTP server
  - HTTP reranker provider
  - CLI serve/probe commands
  - managed wrapper/unit status integration
  - targeted tests and managed smoke
- Follow-up:
  - config template defaults for profile-specific HTTP providers
  - rollout orchestration that can require warm inference before BGE backfill/search
  - multi-client MCP load testing against a fully HTTP-backed BGE profile

## Acceptance Criteria

- `slack-mirror search inference-serve` starts a loopback HTTP service.
- `slack-mirror search inference-probe --smoke` verifies health, embedding smoke, and rerank smoke.
- `build_reranker_provider` supports `provider.type=http`.
- Managed `user-env update` writes an inference wrapper and service unit.
- Runtime status/check-live report inference unit-file presence without making the release `baseline` dependent on the service being active.

## Definition Of Done

- Code, tests, docs, roadmap, and runbook are updated in one slice.
- Targeted tests pass.
- Planning audit passes.
- Release check with managed runtime passes or any residual warning is explicitly classified.

## Completion Notes

- Added `slack_mirror.service.inference`, a loopback-only HTTP service supporting `embed_texts`, `rerank_score`, and health probes.
- Added `search inference-serve` and `search inference-probe`.
- Added HTTP reranker-provider support to match the existing HTTP embedding-provider contract.
- Managed `user-env install/update/rollback` now writes `slack-mirror-inference` and `slack-mirror-inference.service`.
- Managed status/check-live now report inference wrapper and unit-file presence without requiring the service to be active for `baseline`.
