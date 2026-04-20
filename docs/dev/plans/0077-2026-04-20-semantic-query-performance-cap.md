# 0077 | Semantic Query Performance Cap

State: CLOSED
Roadmap: P10
Opened: 2026-04-20
Closed: 2026-04-20

## Current State

- `0076` proved managed `local-bge` and `local-bge-rerank` are CUDA-available after `user-env update --extra local-semantic`.
- `default` has complete `baseline` coverage and a bounded partial BGE rollout of `500` messages plus `500` derived-text chunks.
- Full-corpus profile timing remains too slow for interactive CLI/API/MCP use, with the latest measured query showing roughly `42.5s` baseline and `49.0s` partial BGE.
- Code inspection shows message semantic search computes a bounded `candidate_limit`, but the SQLite adapter currently ignores that limit and returns every embedding row for the workspace/model.
- Follow-up profiling showed the dominant cost was derived-text semantic SQL projecting duplicated full document bodies for chunk candidates; the vector math itself was not the bottleneck.

## Scope

- Enforce the existing message semantic candidate cap at the SQLite adapter boundary.
- Keep chunk-backed derived-text semantic queries on chunk text and stored embeddings instead of projecting full document text for every chunk candidate.
- Keep the fix inside the current SQLite exact-scan path; do not introduce a vector extension, ANN service, or new storage backend in this slice.
- Preserve release-default `baseline` semantics and named retrieval-profile behavior.
- Measure managed `default` latency after the cap is enforced.

## Non-Goals

- Do not broaden BGE rollout.
- Do not promote `local-bge` or learned reranking to the default profile.
- Do not choose or install a SQLite vector extension in this slice.
- Do not add a long-lived inference service yet; this slice only removes the known unbounded scan bug.

## Tracks

- Critical path:
  - wire plan/roadmap/runbook
  - enforce `candidate_limit` in message semantic SQL
  - add targeted regression coverage
  - run local tests and managed timing smoke
- Parallelizable follow-up, not in this slice:
  - SQLite-native vector extension evaluation
  - long-lived local inference service design
  - richer benchmark fixtures for promoted BGE evaluation

## Acceptance Criteria

- Message semantic candidate retrieval honors its requested cap.
- Chunk-backed derived-text semantic results retain matched chunk snippets without carrying duplicated full document text.
- Existing corpus search tests continue to pass.
- A targeted test proves the adapter does not return an unbounded embedding set.
- Managed `default` scale-review timing is rerun and recorded without exposing private Slack message content.

## Definition Of Done

- Code, tests, roadmap, and runbook are updated in one slice.
- Planning audit passes.
- Relevant targeted tests pass.
- Release check remains healthy or any residual failure is explicitly classified.

## Result

- Message semantic candidate retrieval now honors `candidate_limit`.
- Chunk-backed derived-text semantic query projection now omits full document text and uses the matched chunk text for result snippets.
- Local live-stage timing for `default` changed from:
  - message semantic: about `169-216 ms`
  - derived-text semantic: about `40,158 ms` before the projection fix, about `19 ms` after it
- Managed `default` scale-review after refreshing the user install measured:
  - `baseline`: `p95=396.445 ms`
  - partial `local-bge`: one warm run at `283.057 ms`, one cold/model-load run at `15704.844 ms`
- Conclusion:
  - baseline exact SQLite search is now interactive for the measured query
  - broad BGE remains blocked on long-lived local inference lifecycle, not on the baseline SQLite exact-scan path
