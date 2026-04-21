# HTTP-Backed BGE Profile Rehearsal

State: CLOSED
Roadmap: P10
Opened: 2026-04-20

## Current State

- `0078` added a loopback-only local inference service and HTTP-backed embedding/reranker provider contracts.
- The release `baseline` profile remains local-hash and must stay the default.
- The existing `local-bge` profile still uses in-process `sentence_transformers`, so CLI/API/MCP clients can still pay model cold-load cost directly.
- The managed inference service currently starts and smokes with `local-hash-128`, but BGE-through-HTTP has not been proven end to end.

## Scope

- Add explicit HTTP-backed BGE retrieval profile variants without silently changing existing `local-bge` semantics.
- Ensure the inference service can serve `BAAI/bge-m3` embedding requests through the HTTP provider path even when the global baseline provider is local-hash.
- Update config examples and docs so operators can distinguish in-process BGE from warm-service BGE.
- Run a bounded managed smoke against the installed user-scoped runtime.

## Non-Goals

- Do not make any BGE profile the release default.
- Do not broaden BGE embedding rollout beyond existing bounded rehearsal coverage.
- Do not enable learned reranking by default.
- Do not introduce vector database, ANN, or SQLite vector-extension work in this slice.

## Acceptance Criteria

- `search profiles` exposes an explicit HTTP-backed BGE profile.
- `search provider-probe --retrieval-profile <http-bge-profile> --smoke --json` can use the local inference service.
- The managed inference service can embed `BAAI/bge-m3` over HTTP without each client loading the model independently.
- Docs, roadmap, and runbook describe the new profile and validation evidence.

## Definition Of Done

- Code, tests, docs, roadmap, and runbook are updated.
- Targeted tests pass.
- Planning audit passes.
- Managed smoke is run and recorded, or any blocker is explicitly classified.

## Completion Notes

- Added explicit `local-bge-http` and `local-bge-http-rerank` profiles.
- The inference service now dynamically routes `BAAI/bge-m3` embedding requests to a cached sentence-transformers provider even when the global baseline provider is local-hash.
- HTTP reranker requests can carry a `model`/`model_id`, allowing the loopback service to keep the CrossEncoder reranker warm.
- Managed `local-bge-http` smoke proved cold-to-warm behavior:
  - cold BGE HTTP embed smoke: `14167.488 ms`
  - warm BGE HTTP embed smoke: `119.363 ms`
- Managed `local-bge-http-rerank` smoke proved cold-to-warm reranker behavior:
  - cold HTTP reranker smoke: `6800.081 ms`
  - warm HTTP reranker smoke: `133.59 ms`
- Managed scale review for `baseline,local-bge-http` on `default` and query `incident review`:
  - `baseline` p95: `878.193 ms`
  - `local-bge-http` p95: `505.873 ms`
