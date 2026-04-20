# Reranker Provider Seam

State: CLOSED
Roadmap: P10
Opened: 2026-04-19

## Scope

Add the repo-owned reranker seam needed before introducing a learned local reranker.

This slice covers:

- a shared reranker provider contract
- migration of the existing heuristic message reranker behind that contract
- optional reranking for corpus search over message plus derived-text candidates
- CLI/API/MCP plumbing for bounded corpus rerank controls

This slice does not cover:

- loading `BAAI/bge-reranker-v2-m3`
- a long-lived inference service
- reranker model rollout on live data
- changing default search behavior

## Current State

- `0059` and `0060` made derived-text chunk embeddings and evaluation first-class
- reranking now sits behind `slack_mirror.search.rerankers`
- the shipped providers are `heuristic` and `none`
- message search preserves the existing heuristic behavior through the shared provider boundary
- corpus search can now opt into bounded reranking over fused message plus derived-text candidates
- CLI, API, and MCP corpus-search surfaces now expose explicit rerank controls
- learned local reranker loading remains a follow-on slice behind the provider seam

## Outcome

- Added the shared reranker provider contract and row-reranking helpers.
- Migrated message reranking away from the private keyword helper.
- Added opt-in corpus reranking for single-workspace and all-workspace searches without changing defaults.
- Added rerank controls to `search corpus`, HTTP corpus-search endpoints, and the MCP `search.corpus` tool.
- Documented the seam and generated the CLI reference.

## Goals

1. Move reranking behind an explicit provider boundary.
2. Preserve the current heuristic behavior for message search.
3. Add bounded corpus reranking without changing defaults.

## Planned Changes

### 1. Provider seam

- add a shared reranker provider interface
- add `none` and `heuristic` implementations
- add helper functions to rerank row dictionaries consistently

### 2. Search integration

- replace the private message heuristic reranker with the shared provider
- add optional rerank controls to corpus search
- preserve existing ordering when rerank is not requested

### 3. Transport and docs

- expose corpus rerank controls through CLI, API, and MCP
- document that this slice is a seam and heuristic baseline, not the learned reranker rollout

## Acceptance Criteria

- message search reranking still works through the existing `--rerank` path
- corpus search can rerank top-K fused candidates when explicitly requested
- API and MCP corpus search can pass the same bounded rerank controls
- tests cover the shared reranker seam and corpus rerank behavior
- roadmap, runbook, generated CLI docs, and user docs are updated

## Validation Plan

- targeted search tests for message and corpus reranking
- targeted service/API/MCP/CLI tests for rerank parameter plumbing
- `python -m py_compile` for touched modules
- generated CLI docs check
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
