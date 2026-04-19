# Derived-Text Chunk Embeddings

State: CLOSED
Roadmap: P10
Opened: 2026-04-19

## Scope

Extend the local semantic stack from messages into persisted derived-text chunk embeddings.

This slice covers:

- DB-backed storage for derived-text chunk embeddings
- repo-owned helpers for bounded derived-text chunk embedding backfill
- semantic derived-text search over stored chunk vectors instead of on-the-fly embedding
- bounded CLI/operator surfaces for derived-text chunk rollout

This slice does not cover:

- reranking
- ANN/vector-index changes
- multimodal embedding models
- a full derived-text corpus rollout on the live DB in the same slice

## Current State

- message embeddings now support bounded `BAAI/bge-m3` rollout and model-aware readiness under `0058`
- derived-text chunks already exist in the DB and power chunk-aware lexical search
- this slice is now complete:
  - derived-text chunk embeddings are persisted in SQLite per chunk and model id
  - semantic derived-text search prefers stored chunk vectors while keeping a bounded fallback for rows without stored vectors
  - extraction jobs and a dedicated backfill command can both roll out chunk embeddings under the configured semantic model
  - readiness and health now expose configured-model chunk coverage for `attachment_text` and `ocr_text`

## Goals

1. Persist derived-text chunk embeddings under the same local-first provider/model seam as messages.
2. Make semantic derived-text search use stored chunk embeddings first.
3. Add a bounded rollout path for existing derived-text rows and integrate new extraction work cleanly.

## Planned Changes

### 1. Storage

- add a canonical table for derived-text chunk embeddings
- add DB helpers for upsert and retrieval keyed by chunk and model id

### 2. Sync / rollout

- add bounded backfill for derived-text chunk embeddings
- optionally embed newly extracted derived-text chunks during `process-derived-text-jobs`
- expose a CLI rollout path for existing derived-text rows

### 3. Search

- make `search_derived_text_semantic` use stored chunk embeddings with model/provider-aware query vectors
- keep a bounded fallback for rows without stored chunk vectors where necessary
- thread model/provider controls through derived-text and corpus search surfaces

## Acceptance Criteria

- derived-text chunk embeddings are persisted in SQLite under repo-owned schema and helpers
- semantic derived-text search uses stored chunk vectors
- the repo has a bounded CLI/operator path for rolling out chunk embeddings
- tests cover storage, backfill, and semantic search over stored chunk embeddings
- roadmap, runbook, and docs are updated in the same slice

## Validation Plan

- targeted DB tests for derived-text chunk embedding storage
- targeted search tests for semantic derived-text search using stored embeddings
- targeted CLI parse and helper tests for bounded chunk rollout
- `python -m py_compile` for touched modules
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
