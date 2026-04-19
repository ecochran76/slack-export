# Semantic Provider And Model Seam Hardening

State: CLOSED
Roadmap: P10
Opened: 2026-04-19

## Scope

Open the semantic-retrieval lane with the smallest useful architectural slice:

- replace the current duplicated local-hash embedding logic with one explicit embedding-provider seam
- make provider/model resolution an owned shared concern rather than an incidental `model_id` string threaded through callers
- preserve current CLI, API, and MCP contracts while making stronger local models possible in follow-on slices

This plan covers:

- embedding-provider abstraction for message and derived-text semantic paths
- one shipped baseline provider that preserves current behavior
- search-path and sync-path refactors needed to consume that provider seam
- focused regression coverage and docs updates for the new baseline

This plan does not include:

- shipping `bge-m3` or another real local embedding model yet
- adding a learned reranker
- changing the public search command/API/MCP argument surface
- trying to solve derived-text coverage gaps in the same slice

## Current State

- semantic search now has a dedicated shared embedding layer at `slack_mirror.search.embeddings`
- the shipped `local-hash-128` baseline is now resolved and embedded through that one shared seam across:
  - `slack_mirror/sync/embeddings.py`
  - `slack_mirror/search/keyword.py`
  - `slack_mirror/search/derived_text.py`
  - `slack_mirror/search/dir_adapter.py`
- the current local baseline works acceptably for some exact-match queries but performs poorly on paraphrase-style retrieval in live audits
- there is already a strong repo pattern for narrow provider seams in `slack_mirror.sync.derived_text`
- the live audit on 2026-04-19 also confirmed that message embeddings are populated and functioning operationally, so this slice can focus on architecture and behavior preservation first
- remaining work after this slice is the real relevance upgrade:
  - stronger local embedding models
  - learned reranking
  - better derived-text coverage and evaluation depth

## Target Outcome

After this slice:

- semantic embedding behavior is owned by one explicit provider/model seam
- current callers still work with `local-hash-128`
- follow-on local model work can add real providers without rewriting every search and sync path again
- the repo has tests that lock in the new seam and the preserved baseline semantics

## Design Constraints

- keep ownership narrow:
  - provider resolution belongs in a dedicated semantic/embedding layer
  - sync and search code consume that layer rather than reimplementing embedding logic
- do not widen the public search surface yet
- keep `local-hash-128` as the default functional baseline in this slice
- preserve the SQLite-first architecture and current persistence model

## Acceptance Criteria

- one shared embedding-provider seam exists and is used by both sync-time embedding generation and query-time semantic retrieval
- duplicated local hash embedding code is removed from the current search/sync modules
- current search/sync tests pass with the new seam
- at least one new regression test proves the shared provider seam is actually used
- roadmap and runbook are updated in the same slice

## Validation Plan

- targeted tests:
  - `uv run python -m unittest tests.test_search tests.test_embeddings tests.test_app_service -v`
- compile check:
  - `python -m py_compile slack_mirror/search/embeddings.py slack_mirror/sync/embeddings.py slack_mirror/search/keyword.py slack_mirror/search/derived_text.py slack_mirror/search/dir_adapter.py`
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Outcome

- completed in `f967952`:
  - `feat(search): add shared embedding provider seam`
