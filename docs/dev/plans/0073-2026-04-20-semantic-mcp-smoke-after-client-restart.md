# Semantic MCP Smoke After Client Restart

State: CLOSED
Roadmap: P11
Opened: 2026-04-20
Closed: 2026-04-20

## Scope

Run a connected MCP smoke pass after client restart, focused on semantic-search and relevance controls.

This slice covers:

- MCP runtime sanity after reconnect
- MCP tool visibility for semantic profiles and semantic readiness
- workspace and all-workspace semantic readiness
- corpus search in semantic, hybrid, `rrf`, and rerank modes
- search-health gates with and without configured benchmark datasets
- documentation of observed relevance behavior and release-blocking gaps

This slice does not include:

- changing semantic provider policy
- installing optional local semantic dependencies
- running heavy BGE backfills
- broad query-quality tuning beyond smoke-test evidence

## Current State

- `0072` fixed the user-bus environment issue found during live MCP acceptance
- the previous long-lived MCP session had stale tool visibility until client restart
- the restarted MCP session sees `search.profiles` and `search.semantic_readiness`
- release default remains the `baseline` local-hash profile; `local-bge` and `local-bge-rerank` are explicit opt-in profiles
- connected MCP runtime smoke passes for service health, runtime status, live validation, semantic profile listing, semantic readiness, search readiness, corpus search, and search health
- `runtime.status` reports `mcp_ready=true`, `mcp_multi_client_ready=true`, and `clients=4`
- `runtime.live_validation(require_live_units=true)` reports `pass_with_warnings` with one `EMBEDDING_PENDING` warning on `default`
- `search.semantic_readiness` reports all three workspaces ready for the release `baseline` profile:
  - `default`: `91,566/91,566` message embeddings for `local-hash-128`
  - `pcg`: `19,994/19,994` message embeddings for `local-hash-128`
  - `soylei`: `18,925/18,925` message embeddings for `local-hash-128`
- `local-bge` and `local-bge-rerank` report provider-unavailable in the managed environment because `sentence_transformers` and `torch` are not installed there
- `search.readiness` and no-dataset `search.health` pass for `pcg` and `soylei`
- `default` no-dataset `search.health` passes with warnings because derived-text extraction still has `99` attachment-text and `45` OCR jobs pending
- corpus search works through MCP in semantic, lexical, hybrid, `rrf`, all-workspace, and heuristic-rerank modes
- the release `baseline` local-hash semantic mode is transport-healthy but relevance is weak on conceptual queries; lexical and hybrid/RRF are materially stronger when exact terms are present
- passing `model=BAAI/bge-m3` directly to `search.corpus` fails under the current local-hash provider, so MCP callers cannot yet select the `local-bge` profile through the corpus-search tool

## Acceptance Criteria

- connected MCP `tools/list` equivalent exposes semantic profile/readiness tools through this session: met by successful `search.profiles` and `search.semantic_readiness` calls
- `search.profiles` returns release/default and opt-in semantic profiles: met
- `search.semantic_readiness` reports workspace and all-workspace state without error: met
- `search.corpus` works in semantic and hybrid modes through MCP: met
- `search.health` reports pass/fail status through MCP: met
- smoke findings are recorded in this plan and the runbook: met

## Validation Plan

- connected MCP tool calls:
  - `health`
  - `runtime.status`
  - `search.profiles`
  - `search.semantic_readiness`
  - `search.readiness`
  - `search.corpus`
  - `search.health`
- `uv run python -m unittest tests.test_mcp_server -v`
- `uv run slack-mirror release check --require-managed-runtime --json`
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Smoke Results

- MCP connection and tool visibility:
  - `health`: passed
  - `runtime.status`: passed with active API, daemon, webhook, and timer units; runtime-report service remains expected oneshot inactive
  - `runtime.live_validation(require_live_units=true)`: `pass_with_warnings`, warning only for `default` embedding pending
- Semantic profiles:
  - `baseline`: non-experimental `local-hash-128` profile; ready across all workspaces
  - `local-bge`: experimental profile; provider unavailable in the managed environment
  - `local-bge-rerank`: experimental profile; provider and reranker unavailable in the managed environment
- Search readiness:
  - `pcg`: pass, no derived-text pending jobs
  - `soylei`: pass, no derived-text pending jobs
  - `default`: pass with warnings for pending derived-text extraction jobs
- Search behavior:
  - baseline semantic mode executes successfully but returns noisy conceptual matches
  - lexical mode finds exact-term results reliably
  - hybrid/RRF combines sources and preserves exact lexical hits when present
  - `rerank=true` currently uses the heuristic reranker unless the experimental reranker provider is installed and selected outside the release baseline
  - all-workspace hybrid/RRF search executes successfully
  - direct `model=BAAI/bge-m3` corpus search fails with `INVALID_REQUEST` under the local-hash provider, confirming profile-driven dense search is not yet an MCP corpus-search contract
- Benchmark health:
  - no-dataset `search.health` is usable as a readiness gate
  - the checked benchmark fixtures fail against the current live `default` corpus, with zero hits and p95 around `1.4-1.5s`
  - that benchmark failure is useful signal for the semantic-upgrade lane, but it is not an MCP transport failure

## Follow-Ups

- Keep the first stable MCP release on the `baseline` profile.
- Treat BGE/reranker install, GPU model lifecycle, dense index backfill, and query-quality benchmarks as `P10` follow-on work.
- Consider adding a retrieval-profile selector to MCP `search.corpus` before advertising profile-driven dense semantic search to agent clients.
- Clear or process the pending `default` derived-text extraction queue before using derived-text benchmarks as a release-quality gate.
