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

### Phase 1

Completed:

- shared embedding-provider seam (`0053`)

### Phase 2

Next implementation slice:

- local embedder integration for messages using `bge-m3`
- bounded local inference adapter
- evaluation on the known failing paraphrase queries

### Phase 3

- derived-text chunk embeddings
- chunk-level dense retrieval
- readiness and backlog reporting for the stronger embedding path

### Phase 4

- local reranker integration using `bge-reranker-v2-m3`
- top-K rerank path over fused candidates

### Phase 5

- Slack-specific evaluation suite and relevance gates
- operator diagnostics for model health, backlog, and fallback mode

### Phase 6

- latency and scale review
- optional ANN/index backend evaluation if exact dense retrieval is no longer sufficient

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
