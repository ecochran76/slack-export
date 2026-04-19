# BGE-M3 Bounded Message Rollout

State: CLOSED
Roadmap: P10
Opened: 2026-04-19

## Scope

Turn the successful `0057` rehearsal into a repo-owned bounded rollout path for message embeddings.

This slice covers:

- bounded `mirror embeddings-backfill` controls for channel- and time-scoped message rollout
- model-aware readiness and health reporting for partial semantic-model coverage
- operator-facing docs for running a bounded `BAAI/bge-m3` rollout on live data

This slice does not cover:

- derived-text chunk embeddings
- learned reranking
- a full-corpus `bge-m3` migration
- a dedicated long-lived inference adapter process

## Current State

- `0055` added a provider-routed message embedding path for `sentence_transformers`
- `0056` added GPU/runtime probing and provider-aware benchmark plumbing
- `0057` proved on a temporary DB copy that `BAAI/bge-m3` materially improves the known weak paraphrase cases
- the shipped rollout surface is still too blunt:
  - `mirror embeddings-backfill` only supports workspace-wide latest-first scans
  - readiness reports total embedding counts, not coverage for the configured semantic model
- without bounded rollout controls plus model-aware readiness, a partial `bge-m3` migration is hard to operate safely

## Outcome

Completed:

- `mirror embeddings-backfill` now supports bounded rollout by:
  - channel IDs
  - oldest/latest timestamp bounds
  - explicit scan order
  - structured JSON output
- search readiness and health now report message embedding coverage for the configured semantic model, not only total embeddings
- `search health` now warns with `MESSAGE_MODEL_COVERAGE_INCOMPLETE` when the configured semantic model is only partially rolled out
- operator docs now describe the intended bounded `BAAI/bge-m3` rollout loop

## Goals

1. Make bounded live rollout of `BAAI/bge-m3` messages practical without a custom one-off script.
2. Make readiness and health reporting truthful for the configured semantic model during a partial rollout.
3. Keep the implementation inside the existing CLI/app/search seams.

## Planned Changes

### 1. Bounded message rollout controls

Extend `mirror embeddings-backfill` and the underlying sync helper to support:

- optional channel filters
- optional `oldest` and `latest` timestamp bounds
- explicit scan order
- structured output suitable for operator repetition

### 2. Model-aware readiness

Extend app-service readiness and health output so it reports:

- total message embeddings
- embeddings for the configured semantic model
- model coverage ratio against live message count
- per-model message embedding counts
- an explicit warning when the configured model is only partially rolled out

### 3. Operator workflow docs

Document the intended bounded rollout loop for `BAAI/bge-m3` message migration:

1. probe runtime and GPU readiness
2. run channel- or time-bounded embedding backfill
3. inspect readiness and health
4. repeat in bounded slices

## Acceptance Criteria

- `mirror embeddings-backfill` can target a bounded subset of messages without one-off scripts
- readiness/health output distinguishes total embeddings from configured-model coverage
- partial `BAAI/bge-m3` rollout is visible as a warning state rather than silently looking complete
- roadmap, runbook, and operator docs are updated in the same slice

## Validation Plan

- targeted unit tests for bounded embedding backfill filters
- targeted unit tests for model-aware readiness and health output
- targeted CLI parse tests for the new rollout flags
- `python -m py_compile` for touched Python modules
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
