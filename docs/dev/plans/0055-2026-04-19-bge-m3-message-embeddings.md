# BGE-M3 Message Embeddings

State: CLOSED
Roadmap: P10
Opened: 2026-04-19

## Scope

Ship the first real local semantic model path for messages only.

This plan covers:

- a provider-routed semantic embedding layer for message embeddings
- optional local `bge-m3` support without making heavy ML dependencies mandatory for baseline installs or CI
- threading the provider through message embedding jobs and message/corpus semantic search
- focused regression coverage and config/docs updates for the new provider path

This plan does not include:

- derived-text chunk embeddings
- learned reranking
- vector database or ANN adoption
- broad search UX changes

## Current State

- `0053` landed the shared embedding seam
- `0054` documented the local-first retrieval architecture and chose `bge-m3` as the planned embedding family
- current message embeddings still use only the lightweight `local-hash-128` baseline
- current message semantic search still relies on exact cosine over stored SQLite embedding blobs

## Target Outcome

After this slice:

- message embeddings can be produced by either the current local-hash baseline or an optional real local provider
- the repo has a config-driven path for `bge-m3` message embeddings
- message embedding jobs and message/corpus semantic search both resolve through the same provider-routing contract
- the stronger provider remains optional so existing installs and CI continue to work without mandatory ML runtime dependencies

## Outcome

This slice is complete.

Landed:

- provider-routed message embeddings through `slack_mirror.search.embeddings`
- optional local `sentence_transformers` provider support for models such as `BAAI/bge-m3`
- provider threading through:
  - message embedding backfill jobs
  - queued message embedding processing
  - message semantic search
  - message-backed corpus search
- service and CLI resolution of the configured message embedding provider
- focused regression coverage for provider routing without forcing heavy ML dependencies in CI

Kept intentionally out of scope:

- derived-text chunk embeddings
- learned reranking
- ANN or vector-database changes
- forced heavy ML runtime requirements for default installs

## Design Constraints

- keep SQLite as canonical storage
- keep provider-specific model lifecycle in a narrow semantic layer
- do not force heavy ML dependencies for default installs
- do not widen public CLI/API/MCP argument semantics beyond config-driven provider/model selection already present
- keep derived-text semantic retrieval on the current baseline for now

## Acceptance Criteria

- a semantic embedding provider router exists for message embeddings with at least:
  - local hash baseline
  - optional local `bge-m3` path
  - config-driven provider selection
- message embedding jobs and message semantic search use the provider router instead of assuming the local hash path
- corpus search inherits the stronger message semantic path without changing its public contract
- focused tests cover provider routing and preserve the current baseline behavior when heavy ML dependencies are absent
- roadmap, runbook, and relevant docs are updated in the same slice

## Validation Plan

- targeted tests:
  - `uv run python -m unittest tests.test_search tests.test_embeddings tests.test_app_service tests.test_cli -v`
- compile check:
  - `python -m py_compile slack_mirror/search/embeddings.py slack_mirror/sync/embeddings.py slack_mirror/search/keyword.py slack_mirror/search/corpus.py slack_mirror/service/app.py slack_mirror/cli/main.py`
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
