# Phase E — Semantic Search Plan

Status: **approved / in progress** (2026-02-24)

## Objective

Add semantic retrieval to `slack-mirror` without regressing existing keyword search.

Primary outcome:
- support `lexical`, `semantic`, and `hybrid` retrieval modes,
- keep current filter semantics (`from:`, `channel:`, `before/after`, `is:*`, etc.),
- provide measurable quality and latency gates before making hybrid default.

---

## v1 Architecture

1. **Embeddings store** (new DB table)
2. **Embedding pipeline** (incremental + backfill)
3. **Hybrid query planner**
   - lexical candidate set (FTS/SQL)
   - semantic candidate set (vector similarity)
   - score fusion + metadata boosts
4. **CLI/config plumbing** with explicit mode switches

---

## Implementation Approach for Current Codebase

Current runtime DB is SQLite, so Phase E is split into two implementation tracks:

### Track A (near-term, default): SQLite-first semantic support

- Store embeddings in a dedicated table (`message_embeddings`) as serialized vectors.
- Use a pluggable ANN adapter:
  - fallback: brute-force cosine on candidate slices,
  - optional: `hnswlib`/`faiss` side index for faster nearest-neighbor retrieval.
- Keep all metadata filtering in existing SQL paths.

### Track B (future-ready): Postgres + pgvector profile

- Keep schema/API boundaries compatible with a future `pgvector` backend.
- If/when storage migrates to Postgres:
  - use `vector` column + HNSW index,
  - run vector filtering/ranking in SQL.

This split avoids blocking semantic search on a storage migration.

---

## Data Model (Phase E.1)

New table (migration target: `0004_message_embeddings.sql`):

- `workspace_id INTEGER NOT NULL`
- `channel_id TEXT NOT NULL`
- `ts TEXT NOT NULL` (message primary key component)
- `model_id TEXT NOT NULL`
- `dim INTEGER NOT NULL`
- `embedding_blob BLOB NOT NULL` (float32 array bytes)
- `content_hash TEXT NOT NULL` (to detect stale embeddings)
- `embedded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`
- PK: `(workspace_id, channel_id, ts, model_id)`

Indexes:
- `(workspace_id, model_id)`
- `(workspace_id, channel_id, ts)`
- `(workspace_id, content_hash)`

---

## Query Pipeline (Hybrid)

For query `q`:

1. Parse filters (reuse current parser).
2. Lexical retrieval: top `N_lex` candidates.
3. Semantic retrieval: top `N_sem` candidates from vector index/search.
4. Merge candidate IDs.
5. Score fusion:
   - `score = a*lexical + b*semantic + c*recency + d*thread + e*link`.
6. Return top `K` sorted rows.

Configurable knobs:
- `search.semantic.enabled`
- `search.semantic.mode_default` (`lexical|hybrid|semantic`)
- `search.semantic.weights.*`
- `search.semantic.candidate_limits.{lexical,semantic}`
- `search.semantic.model`

---

## CLI / UX

- `search keyword ... --mode lexical|semantic|hybrid`
- `search semantic ...` alias for `--mode semantic`
- keep lexical default until gates pass

---

## Evaluation Gates

Build a real-query eval set (30–100 prompts):
- exact token lookups,
- paraphrase/intent queries,
- filter-heavy constrained queries.

Metrics:
- nDCG@10
- MRR@10
- hit@3 / hit@10
- P50/P95 latency

Ship conditions:
1. lexical mode has no regression,
2. hybrid improves semantic-query relevance by agreed delta,
3. latency within target bounds.

---

## PR Plan (execution order)

### PR1 — Schema + embeddings repository scaffolding
- migration for `message_embeddings`
- db helpers for upsert/get stale rows
- tests for write/update semantics

### PR2 — Embedding pipeline (incremental + backfill command)
- queue/enqueue hooks on message upsert/edit
- content hash stale detection
- `mirror embeddings backfill --workspace ...` command
- baseline embedding provider interface

### PR3 — Hybrid retrieval engine
- semantic candidate provider
- fusion scorer and rank merge
- mode flags in `search keyword`
- tests for mode behavior and ranking stability

### PR4 — CLI semantic alias + config knobs + docs
- `search semantic` command alias
- config fields + validation
- completion + generated docs updates

### PR5 — Eval harness + perf instrumentation
- benchmark dataset runner
- latency and candidate-source counters
- release gate checklist in docs

---

## Risks / Mitigations

- **Embedding cost/latency** → batch and cache; incremental updates only.
- **SQLite ANN limits** → adapter boundary for optional HNSW/FAISS acceleration.
- **Ranking regressions** → gated rollout with lexical fallback always available.
- **Operational complexity** → keep defaults minimal; advanced acceleration optional.

---

## Immediate Start Checklist (opened now)

- [ ] Implement PR1 migration and DB helpers
- [ ] Add unit tests for embedding row lifecycle
- [ ] Wire runbook milestone update after PR1 lands
