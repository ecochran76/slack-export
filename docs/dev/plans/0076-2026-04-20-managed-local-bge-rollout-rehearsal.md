# Managed Local-BGE Rollout Rehearsal

State: CLOSED
Roadmap: P10
Opened: 2026-04-20
Closed: 2026-04-20

## Scope

Make the managed user-scoped runtime capable of running the `local-bge` retrieval profile, then run a bounded `default` rollout rehearsal and benchmark comparison against the clean baseline state from `0075`.

This slice covers:

- verify repo and managed runtime dependency state for `sentence_transformers` and `torch`
- check GPU availability before model smoke or backfill work
- install or otherwise enable optional local semantic dependencies in the managed runtime without changing the release default profile
- run `local-bge` provider probe with smoke in the managed runtime
- inspect `default` rollout plan for `local-bge`
- run a bounded `local-bge` message and/or derived-text rollout small enough to avoid monopolizing the workstation
- rerun semantic readiness and targeted benchmark checks to compare readiness, quality, and latency shape
- record whether `local-bge` is ready for broader rollout, needs dependency work, or needs search-index/performance work first

This slice does not include:

- changing `baseline` as the first-release default
- full workspace-wide `BAAI/bge-m3` rollout unless the bounded rehearsal proves it is safe and fast enough
- enabling learned reranking by default
- adding a vector extension or ANN store
- frontend UX changes

## Current State

- `0075` drained the managed `default` baseline backlog.
- MCP `search.readiness` reports `default` baseline ready with complete `local-hash-128` coverage for messages and derived-text chunks.
- Benchmark checks still fail on local-hash ranking quality and full-corpus latency.
- The repo venv has `sentence_transformers` and `torch` installed.
- Before this slice, the managed runtime did not have `sentence_transformers` or `torch` installed, so MCP reported `local-bge` and `local-bge-rerank` as provider-unavailable.
- `nvidia-smi` reports an RTX 5080 with available memory, so bounded local model smoke is reasonable.
- `user-env install` and `user-env update` now support `--extra local-semantic`, keeping the default managed install lightweight while making optional semantic dependencies reproducible.
- The managed runtime was refreshed with `uv run slack-mirror user-env update --extra local-semantic`.
- Post-refresh `local-bge` provider probe passes:
  - `sentence_transformers_installed=true`
  - `torch_installed=true`
  - `cuda_available=true`
  - GPU: `NVIDIA GeForce RTX 5080`
  - smoke: `2` texts, `1024` dimensions, about `10.2s` cold latency
- Post-refresh `local-bge-rerank` reranker probe passes for `BAAI/bge-reranker-v2-m3`.
- Bounded rollout on `default` completed:
  - message embeddings: scanned `500`, embedded `500`, skipped `0`
  - derived-text chunk embeddings: scanned `500`, embedded `500`, skipped `0`
- Semantic readiness after bounded rollout:
  - `baseline`: ready, complete coverage for `91,586` messages and `11,142` derived-text chunks
  - `local-bge`: partial rollout, `500/91,586` messages and `500/11,142` derived-text chunks
  - `local-bge-rerank`: partial rollout with reranker available
- Scale review against one full-corpus query still reports unacceptable latency:
  - `baseline`: about `42.5s` p95 for the measured query
  - `local-bge`: about `49.0s` p95 for the measured query
  - decision: evaluate ANN service after SQLite-native options and prefer a long-lived local inference service for heavy profiles
- Live benchmark fixtures are synthetic and not suitable as success criteria for this real `default` corpus because their expected IDs do not exist in the live DB.

## Acceptance Criteria

- managed-runtime local semantic dependency state is recorded before and after any install step: met.
- `local-bge` provider probe either passes with smoke or fails with a classified blocker: met.
- `default` rollout plan for `local-bge` is recorded before any backfill: met.
- any bounded rollout commands and counts are recorded: met.
- readiness and benchmark outcomes after the bounded rehearsal are recorded: met.
- the slice ends with an explicit recommendation: met; prioritize search-performance/index and long-lived inference work before broad rollout.

## Validation Plan

- `slack-mirror-user search provider-probe --retrieval-profile local-bge --smoke --json`
- `slack-mirror-user mirror rollout-plan --workspace default --retrieval-profile local-bge --limit 500 --json`
- bounded `slack-mirror-user mirror embeddings-backfill --workspace default --retrieval-profile local-bge --limit ... --json` if provider probe passes
- bounded `slack-mirror-user mirror derived-text-embeddings-backfill --workspace default --retrieval-profile local-bge --limit ... --json` if provider probe passes and GPU headroom remains acceptable
- `slack-mirror-user search semantic-readiness --workspace default --json`
- targeted `search health` benchmark checks with `--retrieval-profile local-bge` if coverage is sufficient for the benchmark shape
- `uv run slack-mirror release check --require-managed-runtime --json`
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Implementation Notes

- Added `--extra` to `user-env install` and `user-env update`.
- Extras may be repeated or comma-separated; the first supported operator use is `--extra local-semantic`.
- The managed venv bootstrap now upgrades `setuptools<82` to avoid torch 2.11's `setuptools<82` constraint conflict during semantic installs.
- `baseline` remains the active config and release-safe default. The BGE profiles are available but still partial.
- Do not broaden BGE rollout until full-corpus search stops taking tens of seconds per query or the query path is moved behind a suitable local vector/index and long-lived inference boundary.
