# Local Semantic Retrieval Architecture

State: OPEN
Roadmap: P10
Opened: 2026-04-19

## Scope

Lock the durable architecture for the local-first semantic stack before the repo takes on heavy model integration work.

This plan covers:

- retrieval-stage design for lexical, dense, hybrid, and reranked search
- the local model family choice for the next implementation phases
- the service-boundary decision for embedding and reranking inference
- storage and index strategy for messages and derived text
- rollout phases and evaluation gates

This plan does not include:

- shipping `bge-m3` embeddings yet
- shipping a learned reranker yet
- migrating to a vector database
- solving current derived-text coverage gaps in the same slice

## Current State

- `0053` is complete and provides the shared embedding-provider seam needed for heavier local models
- current semantic retrieval still depends on the lightweight `local-hash-128` baseline and performs poorly on paraphrase-style queries
- lexical retrieval remains the strongest currently shipped signal
- derived-text retrieval is structurally present, but live coverage is still sparse enough that architecture decisions should not assume fully populated attachment embeddings yet
- the repo is SQLite-first today, and CLI, API, and MCP are intentionally thin over shared application logic

## Research Summary

The current external and repo-specific evidence points to this architecture:

- local dense embedder family:
  - `BAAI/bge-m3`
- local reranker family:
  - `BAAI/bge-reranker-v2-m3`
- retrieval shape:
  - lexical retrieval plus dense retrieval plus deterministic fusion plus reranking
- storage shape:
  - keep SQLite as the canonical system of record
- infrastructure shape:
  - avoid a vector-DB migration unless latency and corpus scale prove it necessary later

Reasons:

- `bge-m3` is a strong local fit because it is multilingual, supports longer contexts, and is explicitly designed around dense, lexical, and multi-vector retrieval capabilities
- `bge-reranker-v2-m3` is the paired local reranker in the same family and fits a second-stage reranking role cleanly
- retrieve-then-rerank remains the standard search architecture for quality-sensitive semantic retrieval
- Qdrant and similar systems are viable later, but they widen the architecture substantially beyond the repo’s current SQLite-first ownership model
- a lightweight SQLite-native vector extension may be worth evaluating later, but it should follow measured latency evidence rather than lead the design

## Architecture Decision

### 1. Retrieval Stages

Adopt a staged retrieval pipeline:

1. lexical candidate generation
   - existing SQLite FTS and structured filtering remain first-class
2. dense candidate generation
   - local embeddings over messages and later derived-text chunks
3. candidate fusion
   - start with a deterministic method such as reciprocal rank fusion
4. reranking
   - local cross-encoder reranking over top-K fused candidates
5. projection and grouping
   - return stable message/document/thread-shaped results to CLI, API, and MCP

### 2. Model Decision

Use this family as the planned default local retrieval profile:

- embedder: `BAAI/bge-m3`
- reranker: `BAAI/bge-reranker-v2-m3`

Keep the already shipped `local-hash-128` path as the fallback baseline until the stronger profile is validated.

### 3. Service Boundary

Do not make every CLI, API, daemon, and MCP path own heavy model lifecycle directly.

Planned approach:

- keep the provider seam in repo code
- add a dedicated local inference adapter/service boundary for heavy embedding and reranking models
- allow a simpler in-process implementation only as a bounded stepping stone if needed to prove quality quickly

Default direction:

- thin repo-owned adapter contract
- long-lived local inference process for model loading and requests

### 4. Storage And Index Strategy

Near term:

- keep SQLite as canonical storage
- store dense embeddings in the existing repo-owned persistence path
- continue using exact dense comparison over bounded candidate sets where feasible

Do not do yet:

- full vector-database adoption
- large architectural migration to Qdrant or equivalent

Later evaluation path:

- measure latency and corpus growth
- if exact dense retrieval becomes too expensive, evaluate:
  - SQLite-native vector extensions
  - ANN-backed local services
  - only then a larger vector-DB move

### 5. Hybrid Search Policy

Hybrid search should not mean “dense replaces lexical.”

Planned policy:

- lexical remains a strong retrieval lane
- dense retrieval supplements lexical for paraphrase and concept matching
- reranking becomes the final quality layer
- deterministic fusion keeps operator expectations stable and debuggable

## Planned Rollout

### Phase 1: Provider Seams And Local Model Proof

Completed:

- shared embedding-provider seam (`0053`)
- provider-routed `BAAI/bge-m3` message embedding path (`0055`)
- provider probe and GPU/runtime visibility (`0056`)
- bounded live-data `bge-m3` message rehearsal (`0057`)
- bounded message embedding rollout controls and coverage reporting (`0058`)

Exit state:

- the repo can run stronger local message embeddings without changing the default baseline
- readiness and health distinguish configured-model coverage from legacy embedding coverage
- local workstation capability has been validated without assuming broad rollout safety

### Phase 2: Derived-Text Semantic Coverage

Completed:

- persisted derived-text chunk embeddings (`0059`)
- chunk-level semantic derived-text retrieval (`0059`)
- derived-text benchmark target and chunk-aware query reports (`0060`)

Exit state:

- attachment and OCR text can participate as first-class semantic targets
- coverage gaps are visible separately for messages, attachment text, and OCR text
- evaluation can target derived text directly instead of inferring quality through corpus search

### Phase 3: Reranker Provider And Learned Local Reranker

Completed:

- shared reranker provider seam (`0061`)
- opt-in corpus reranking over fused message plus derived-text candidates (`0061`)
- optional `sentence_transformers` CrossEncoder provider for `BAAI/bge-reranker-v2-m3` (`0062`)
- reranker readiness and smoke probe (`0062`)

Exit state:

- learned reranking is available but not default
- CLI, API, and MCP rerank semantics remain stable
- provider config, not transport contracts, selects heuristic versus learned reranking

### Phase 4: Live Relevance Rehearsal And Benchmark Lock

Completed:

- learned-reranker live rehearsal across bounded live tenant queries (`0063`)
- GPU memory and cold-start observations for `BAAI/bge-reranker-v2-m3` on the RTX 5080 workstation (`0063`)
- decision to keep learned reranking experimental because bounded top-1 quality did not improve enough to justify rollout (`0063`)

Exit state:

- learned reranking is technically viable but not recommended as a default
- rollout controls should lead before broader semantic backfill or reranker promotion

Original purpose:

- prove whether `bge-m3` plus learned reranking improves real Slack search quality enough to justify operator rollout
- turn ad hoc quality checks into durable benchmark artifacts

Work packages:

1. Query set design:
   - collect real tenant search scenarios across exact-match, paraphrase, attachment/OCR, people/channel filters, and stale operational incidents
   - include negative/control queries where lexical should remain dominant
   - define expected target messages, files, chunks, or threads with stable identifiers
2. Rehearsal harness:
   - run baseline lexical/hybrid, `bge-m3` hybrid, heuristic rerank, and learned rerank variants against the same query set
   - record top-k deltas, hit@k, ndcg/mrr, latency, and GPU memory before/after
   - keep test DB copies or bounded live scopes so rehearsal is repeatable and non-destructive
3. Benchmark promotion:
   - promote high-signal rehearsal cases into repo-owned benchmark JSONL fixtures
   - add a reranked benchmark mode if needed, without changing existing `search health` defaults
4. Decision gate:
   - if learned reranking improves quality within acceptable latency, proceed to rollout controls
   - if quality is mixed or latency is too high, keep it experimental and evaluate a lighter reranker before rollout

Acceptance gates:

- at least one benchmark fixture covers message paraphrase retrieval
- at least one benchmark fixture covers derived-text chunk retrieval
- learned reranker latency and memory are measured on the RTX 5080 workstation
- the decision to proceed, defer, or swap reranker model is recorded in this plan and the runbook

### Phase 5: Rollout Controls And Operator UX

Completed baseline:

- named retrieval profiles for `baseline`, `local-bge`, and experimental `local-bge-rerank` (`0064`)
- profile-aware corpus search, provider probes, reranker probes, and bounded embedding backfill commands (`0064`)
- read-only tenant rollout planning with message and derived-text chunk coverage plus copyable bounded commands (`0064`)
- tenant semantic-readiness diagnostics across CLI, API, MCP, and the authenticated tenant settings page (`0065`)

Remaining purpose:

- make stronger semantic retrieval manageable in normal operations rather than only by expert CLI use

Work packages:

1. Config profiles:
   - named retrieval profiles such as `baseline`, `local-bge`, and `local-bge-rerank` now exist
   - keep profile selection explicit for CLI/API/MCP callers
   - document safe defaults and expected resource cost
2. Backfill orchestration:
   - read-only tenant-scoped rollout planning now emits bounded message and derived-text chunk embedding commands under the selected profile model/provider
   - remaining work is resumable orchestration beyond single bounded CLI commands
   - preserve current SQLite-first persistence
3. Readiness and diagnostics:
   - per-tenant profile readiness now surfaces through CLI/API/MCP and the current authenticated tenant settings page
   - remaining work is richer long-running backfill progress, error counts, and last-probe history once orchestration exists
4. Safe fallback:
   - make fallback mode visible when configured-model coverage is incomplete or the learned provider is unavailable
   - do not silently report strong semantic readiness when the system is using legacy or heuristic paths

Acceptance gates:

- operators can tell whether a tenant is `baseline`, `embedding rollout`, `ready for local semantic`, or `ready for rerank`
- rollback is configuration-only for search behavior
- benchmark and readiness output use the same model/provider names operators see in config

### Phase 6: Query Pipeline Hardening

Completed baseline:

- weighted corpus fusion remains the default (`0066`)
- reciprocal-rank fusion is available as an explicit opt-in corpus fusion method (`0066`)
- corpus results include machine-readable `_explain` metadata with source, fusion method, lane scores, lane ranks, weights, and rerank provider (`0066`)

Purpose:

- improve retrieval quality and debuggability once model choices and rollout controls are proven

Work packages:

1. Fusion policy:
   - deterministic reciprocal-rank fusion is now available for bounded comparison against weighted-score fusion
   - lexical, semantic, hybrid, and rerank scores plus lane ranks are now visible in explain output
   - avoid replacing lexical relevance with dense retrieval for exact-match or filtered queries
2. Thread and document projection:
   - decide when results should return messages, threads, files, chunks, or grouped candidates
   - keep MCP/API result shapes stable while adding richer context fields
3. Advanced controls:
   - expose candidate window sizes, rerank top-K, derived-text kind/source filters, and profile selection consistently across CLI/API/MCP
   - ensure frontend advanced search controls reuse the same contracts
4. Result actionability:
   - `0067` is open to support selecting candidate results for export/report/action workflows without needing another search pass
   - preserve stable result identifiers for message, thread, file, canvas, and chunk targets

Acceptance gates:

- explain output is sufficient to diagnose why a result ranked highly
- API/MCP search contracts remain thin over shared search logic
- frontend and agent clients do not need private ranking logic

### Phase 7: Scale And Inference Boundary Review

Purpose:

- decide whether the current in-process exact-search design is sufficient, or whether the repo needs a stronger local inference/index service

Work packages:

1. Latency and corpus-size review:
   - measure current exact dense comparison cost on real tenant corpus sizes
   - separate query latency from model-load latency and DB scan latency
2. Inference lifecycle:
   - decide whether embeddings and reranking should move from in-process providers to a long-lived local inference service
   - preserve the existing provider contracts so service migration is an implementation detail
3. Index backend evaluation:
   - only if measured latency requires it, evaluate SQLite-native vector extensions first
   - evaluate ANN-backed local services or vector databases only if SQLite-native options do not meet requirements
4. Multi-client behavior:
   - validate concurrent MCP/API/CLI search calls under model-loaded conditions
   - document memory and concurrency limits for 10+ agent clients

Acceptance gates:

- a documented decision exists for staying SQLite/exact, adopting SQLite vector extensions, or adding a local ANN service
- MCP multi-client behavior is validated under the intended semantic profile
- no client path owns private model lifecycle code

### Phase 8: Release And Default Policy

Purpose:

- decide what becomes recommended, what remains experimental, and what ships as release-safe behavior

Work packages:

1. Release profile:
   - choose default installed behavior for user-scoped release
   - likely default remains lexical/hybrid baseline, with local semantic/rerank as explicit opt-in profiles
2. Documentation:
   - publish an operator guide for enabling local semantic retrieval
   - include hardware expectations, backfill steps, readiness gates, and rollback
3. Regression suite:
   - add benchmark checks appropriate for CI without requiring GPU
   - keep GPU/model smoke as local/operator validation, not universal CI
4. Final policy:
   - record when to recommend `bge-m3`
   - record when to recommend learned reranking
   - record when to avoid learned reranking due to latency, memory, or marginal quality

Acceptance gates:

- release docs clearly distinguish baseline, recommended local semantic, and experimental search modes
- operators have one repeatable enablement path and one rollback path
- benchmark health can be used as a gate before enabling stronger retrieval for a tenant

## Dependency Graph

Critical path:

1. Phase 4 live relevance rehearsal.
2. Benchmark fixture promotion.
3. Rollout controls and readiness UX.
4. Query pipeline hardening.
5. Scale/inference boundary decision.
6. Release/default policy.

Parallelizable tracks after Phase 4:

- operator UX and status reporting
- frontend advanced search controls
- benchmark fixture expansion
- inference-service exploration
- export/report result-action integration

Do not parallelize before Phase 4:

- default-profile changes
- vector-index migration
- broad live rollout
- frontend controls that imply learned reranking is production-ready

## Risk Register

- Model load cost:
  - learned reranker may be too slow or memory-heavy for routine MCP use unless kept warm
- Quality ambiguity:
  - reranking can improve paraphrase queries while hurting exact-match/operator queries
- Coverage mismatch:
  - semantic search quality is limited if tenant message or derived-text embeddings are only partially backfilled
- Client concurrency:
  - multiple Codex/OpenClaw clients can create unacceptable cold-start or GPU contention without a long-lived inference boundary
- UI overpromise:
  - frontend status must not imply strong semantic readiness when only baseline or partial coverage exists

## Remaining Plan Slices

Recommended remaining child plans:

- `0065`: tenant semantic readiness diagnostics across CLI/API/MCP/frontend
- `0066`: query fusion and explainability hardening
- `0067`: actionable search results for export/report workflows
- `0068`: scale and inference-boundary review
- `0069`: release profile, docs, and final semantic-search policy

## Acceptance Criteria

- the repo has an explicit architecture decision for local semantic retrieval before heavy model integration
- the chosen retrieval stages, model family, service boundary, and storage strategy are documented clearly enough to guide the next coding slice
- roadmap and runbook reflect the new architecture-first sequencing inside `P10`
- the plan remains bounded and implementation-ready rather than aspirational

## References

- `BAAI/bge-m3` model card:
  - `https://huggingface.co/BAAI/bge-m3`
- `BAAI/bge-reranker-v2-m3` model card:
  - `https://huggingface.co/BAAI/bge-reranker-v2-m3`
- FlagEmbedding project:
  - `https://github.com/FlagOpen/FlagEmbedding`
- Sentence Transformers documentation:
  - `https://sbert.net/`
- Qdrant hybrid/reranking docs:
  - `https://qdrant.tech/documentation/search-precision/reranking-hybrid-search/`
- `sqlite-vec` reference for possible later evaluation:
  - `https://github.com/asg017/sqlite-vec`

## Validation Plan

- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
