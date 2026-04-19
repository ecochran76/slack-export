# Derived-Text Retrieval Evaluation

State: CLOSED
Roadmap: P10
Opened: 2026-04-19

## Scope

Add a repo-owned evaluation path for derived-text retrieval quality now that derived-text chunk embeddings are persisted.

This slice covers:

- benchmark evaluation for derived-text retrieval through the shared search-eval harness
- search-health support for running a derived-text benchmark target explicitly
- chunk-aware debug output so derived-text benchmark results expose matched chunk context
- one shipped benchmark dataset for derived-text smoke coverage

This slice does not cover:

- learned reranking
- ANN/vector-index work
- live rollout of a large derived-text benchmark corpus
- changing corpus-search ranking behavior in the same slice

## Current State

- `0059` is complete and now persists derived-text chunk embeddings under the configured semantic model
- this slice is now complete:
  - the shared eval harness supports a derived-text benchmark target
  - `search health` can run that target explicitly while preserving corpus as the default
  - derived-text benchmark query reports now include chunk-aware debug output for top results
  - a shipped smoke dataset exists at `docs/dev/benchmarks/slack_derived_text_smoke.jsonl`

## Goals

1. Add a first-class derived-text benchmark path to the shared evaluation layer.
2. Make `search health` able to run that target without overloading the corpus benchmark contract.
3. Expose chunk-aware result details so degraded derived-text queries are diagnosable.

## Planned Changes

### 1. Eval harness

- add a derived-text retrieval evaluator alongside message and corpus evaluation
- support lexical and semantic derived-text benchmark modes
- emit stable query reports including source id, label, and chunk-match context

### 2. Search health

- add a benchmark target selector for `corpus` vs `derived_text`
- preserve the existing corpus default
- keep thresholds and failure codes aligned with the existing health contract

### 3. Benchmarks and tests

- add a derived-text smoke benchmark dataset under `docs/dev/benchmarks/`
- add app-service and CLI coverage for the new target
- validate chunk-aware debug output in the benchmark report

## Acceptance Criteria

- the repo can benchmark derived-text retrieval directly through the shared evaluation layer
- `search health` can run a derived-text benchmark target explicitly
- derived-text benchmark query reports expose chunk-aware debug context
- docs and planning are updated in the same slice

## Validation Plan

- targeted app-service tests for derived-text search health and benchmark reporting
- targeted CLI parse/output tests for the benchmark target selector
- `python -m py_compile` for touched modules
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
