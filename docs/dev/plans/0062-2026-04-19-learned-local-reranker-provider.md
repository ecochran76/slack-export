# Learned Local Reranker Provider

State: CLOSED
Roadmap: P10
Opened: 2026-04-19

## Scope

Add the first learned local reranker provider behind the reranker seam shipped in `0061`.

This slice covers:

- a `sentence_transformers` CrossEncoder-backed reranker provider
- config parsing for a learned local reranker model such as `BAAI/bge-reranker-v2-m3`
- a repo-owned reranker probe command with optional smoke scoring
- documentation and tests for the provider contract

This slice does not cover:

- making learned reranking the default
- running broad live-data reranking or tenant rollout
- adding a long-lived model server
- changing benchmark pass/fail thresholds for existing search health

## Current State

- `0061` introduced a shared reranker provider seam.
- The shipped provider implementations now include `heuristic`, `none`, and an optional `sentence_transformers` CrossEncoder provider.
- Message and corpus search can opt into reranking through the same existing `rerank` controls.
- Learned local reranking is selected by config, not by API/MCP transport changes.
- The local workstation has GPU capacity for heavier retrieval models; the new probe reports dependency, CUDA, GPU, and optional smoke-scoring readiness before live use.

## Outcome

- Added `SentenceTransformersCrossEncoderRerankerProvider`.
- Added `probe_reranker_provider(...)`.
- Added `SlackMirrorAppService.reranker_probe(...)`.
- Added `slack-mirror search reranker-probe`.
- Documented learned local reranker config and kept `heuristic` as the default provider.
- Verified dependency/GPU readiness can be inspected without loading the large model.

## Goals

1. Add a learned local reranker provider without changing default search behavior.
2. Make dependency, device, and model readiness inspectable before live use.
3. Keep CLI/API/MCP rerank semantics unchanged: learned reranking is selected by config, not by new transport contracts.

## Planned Changes

### 1. Provider implementation

- add a CrossEncoder provider under `slack_mirror.search.rerankers`
- support model, device, batch size, trust-remote-code, activation, and cache-folder config fields where practical
- preserve `heuristic` as the default provider

### 2. Probe command

- add `slack-mirror search reranker-probe`
- report provider type, model, dependency availability, torch/CUDA visibility, configured device, and optional smoke-scoring latency

### 3. Docs and tests

- document the local learned reranker config and bounded usage loop
- add parser, provider, probe, and service tests
- regenerate generated CLI docs

## Acceptance Criteria

- `search.rerank.provider.type: sentence_transformers` builds a learned reranker provider when dependencies are installed
- missing optional dependencies are reported by probe instead of failing silently
- `search reranker-probe --smoke --json` has a stable machine-readable shape
- existing `--rerank` search transports continue to work without API/MCP schema churn
- roadmap, runbook, user docs, generated CLI docs, and tests are updated

## Validation Plan

- targeted reranker provider and probe tests
- targeted CLI parser tests
- targeted app-service probe tests
- `python -m py_compile` for touched modules
- generated CLI docs check
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
