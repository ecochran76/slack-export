# Phase F — Search Platform Roadmap (Reusable Across Projects)

## Why this phase

Current search is working for Slack mirror, but we should harden it into a reusable search toolkit that can be applied to:
- SQLite/Postgres-backed corpora,
- file-system corpora (Markdown/docs/code/text),
- mixed sources (DB + files + attachments).

## Core principle

Separate **search engine capabilities** from **Slack-specific ingestion**.

---

## F0: Design Goals

1. Reuse across projects (DB or directory corpus)
2. Clear abstraction boundaries (ingest / index / retrieve / rerank / present)
3. Hybrid-first retrieval (lexical + semantic)
4. Predictable quality controls (eval harness + benchmarks)
5. Operational safety (backfill queues, checkpoints, observability)

---

## F1: Quick Wins (high impact, low risk)

### 1) Channel/source include-exclude filters
- Add generalized source scoping syntax:
  - `in:<source1,source2>`
  - `-source:<pattern>`
- Implement at planner level, before semantic retrieval.

### 2) Thread/document grouping mode
- `--group-by-thread` (Slack)
- reusable equivalent: `--group-by-parent` for generic corpora
- collapse near-duplicate hits in same group.

### 3) Strong fielded filtering for semantic mode
- enforce metadata constraints first (source/author/time/type), then vector retrieval.

### 4) Better snippets/explanations
- lexical match highlights
- semantic “why” hints (nearest terms / centroid labels)

---

## F2: Reusable Search Abstraction Layer

Create a generic package layer (e.g. `slack_mirror/search/platform/`) with these interfaces:

- `CorpusAdapter`
  - list documents/chunks
  - resolve metadata fields
  - fetch content by id
- `LexicalIndex`
  - candidate retrieval API
- `VectorIndex`
  - embedding upsert/query API
- `QueryPlanner`
  - filter parsing + retrieval strategy selection
- `FusionRanker`
  - weighted score merge
- `ResultPresenter`
  - snippets/grouping/explain formatting

Slack-specific code implements adapters; future projects reuse engine + adapters.

---

## F3: Universal Corpus Ingestion (DB + directory)

### DB corpus adapter
- generic SQL adapter configurable by:
  - table name
  - id fields
  - text field
  - metadata mapping

### Directory corpus adapter
- recursively index files by glob / mime
- optional chunking strategies for large files
- metadata: path, mtime, extension, project, tags

### Attachment/document adapter
- OCR/text extraction pipeline for PDFs/images/canvases
- same embedding + lexical pathways

---

## F4: Retrieval Quality Upgrades

1. Reranker stage (optional flag)
   - cross-encoder rerank top-N candidates
2. Time-intent parser
   - natural language time filters (“last year”, “recent”)
3. Query profiles
   - saved presets for scopes, weights, reranker mode
4. Auto-tuning
   - optimize fusion weights via eval datasets per corpus

---

## F5: Evaluation & Benchmarking (portable)

Extend `scripts/eval_search.py` to support corpus adapters:
- evaluate multiple corpora with same benchmark schema
- metrics:
  - nDCG@k, MRR@k, Hit@k
  - P50/P95 latency
  - source-mix diagnostics

Dataset schema (reusable):
```json
{"query":"...","relevant":{"doc_or_msg_id":2},"scope":{"source":["general"]}}
```

---

## F6: Observability & Ops

- queue lag + throughput for embeddings
- index freshness checks
- retrieval diagnostics
  - candidate counts by stage
  - score components
- health command
  - `search health` across lexical/vector/eval readiness

---

## Proposed implementation sequence

### PR-F1
- include/exclude source filters
- strict semantic fielded filter enforcement

### PR-F2
- thread/grouping mode + duplicate collapse
- improved snippet/explain output

### PR-F3
- search platform interfaces (`CorpusAdapter`, `LexicalIndex`, `VectorIndex`, etc.)
- refactor Slack search to adapter implementation

### PR-F4
- directory corpus adapter + CLI (`search index-dir`, `search query-dir`)

### PR-F5
- portable eval harness upgrades + docs + baseline benchmark packs

### PR-F6
- optional reranker and query profiles

---

## Reuse deliverables for future projects

1. **Search platform module** (adapter-based retrieval engine)
2. **Portable eval harness** and dataset schema
3. **Operational playbook** for hydration/indexing/benchmarking
4. **Config templates** for DB corpora and directory corpora
5. **Lessons-learned doc** (what affected precision/latency most)

---

## Success criteria for Phase F

- Same search engine can run on:
  - Slack DB corpus
  - local docs directory corpus
- No major regression in current Slack search relevance
- Quality benchmarks reproducible across corpora
- Feature portability demonstrated with at least one non-Slack corpus
