# Learned Reranker Live Rehearsal

State: CLOSED
Roadmap: P10
Opened: 2026-04-19

## Scope

Run a bounded, evidence-backed rehearsal of learned local reranking against real tenant search data before changing defaults or broadening rollout.

This slice covers:

- learned reranker dependency/GPU readiness checks
- bounded search comparisons across baseline, local semantic, heuristic rerank, and learned rerank modes
- latency and GPU-memory observations around reranker load/scoring
- promotion of high-signal rehearsal cases into durable benchmark fixtures when results are stable enough
- a recorded proceed/defer/swap decision for learned reranking

This slice does not cover:

- making learned reranking the default
- broad tenant rollout
- vector-index or inference-service migration
- frontend controls
- changing existing API/MCP schemas

## Current State

- `0062` added an optional `sentence_transformers` CrossEncoder reranker provider.
- The managed install still defaults to `local-hash-128` for semantic embeddings and `heuristic` for reranking.
- Managed tenants currently have full `local-hash-128` message coverage, but no `BAAI/bge-m3` message coverage and no derived-text chunk coverage in live tenant DBs.
- Existing repo benchmark fixtures cover synthetic corpus and derived-text scenarios, but not learned reranker live-data quality.
- Learned reranker smoke and bounded live-message comparisons were run read-only.

## Rehearsal Result

Decision: defer learned-reranker rollout.

Reasons:

- Learned CrossEncoder reranking is technically viable on the RTX 5080 workstation.
- Cold learned-reranker smoke/warmup took about 10.8-15.7 seconds depending on run state.
- Warm learned-rerank query latency ranged from about 70 ms to about 2.0 s on the bounded query set.
- GPU memory increased from about 4.7 GiB used to about 7.2 GiB after model warmup, and about 8.2 GiB after bounded query scoring.
- Top-1 result did not improve on the four bounded live-message queries tested.
- Lower-rank changes were mixed and not clearly better without stronger labeled relevance fixtures.
- The managed DBs do not yet have `BAAI/bge-m3` coverage, so this was not a full planned `bge-m3` plus learned-reranker profile test.

Queries tested:

| Label | Workspace | Query | Top-1 changed? | Notable result |
| --- | --- | --- | --- | --- |
| `default_nylon_research` | `default` | `nylon research` | no | learned rerank preserved top-1 but moved a lower `oc-dev-slack-export` result into top 5 |
| `pcg_invoice` | `pcg` | `invoice` | no | learned rerank swapped lower invoice-related ranks but did not improve top-1 |
| `pcg_review_rubric` | `pcg` | `review rubric` | no | learned rerank preserved top-1 and produced mixed lower-rank changes |
| `soylei_website` | `soylei` | `website` | no | learned rerank preserved top-1 and moved one non-website-channel result into top 5 |

No benchmark fixture was promoted in this slice because the live evidence did not show a stable relevance improvement.

Next decision:

- Do not make learned reranking recommended or default yet.
- Proceed to rollout controls and semantic readiness work before another learned-reranker quality pass.
- Revisit learned reranking after a bounded `BAAI/bge-m3` rollout profile and stronger labeled live benchmarks exist.

## Goals

1. Measure whether learned local reranking improves real search quality enough to justify rollout work.
2. Capture latency and GPU-memory cost for the RTX 5080 workstation.
3. Convert stable findings into benchmark or rehearsal artifacts.
4. Record a clear decision for the next semantic-search slice.

## Planned Work

### 1. Readiness and scope

- inspect tenant search readiness for configured model coverage
- probe heuristic and learned reranker readiness
- avoid write/backfill actions unless explicitly needed and bounded

### 2. Query set

- choose a small cross-section of queries:
  - exact-match controls
  - paraphrase/operator incidents
  - message-centric queries
  - derived-text or attachment/OCR queries where coverage exists
- prefer queries with known targets from existing benchmark fixtures or live result inspection

### 3. Rehearsal comparison

Compare variants where data coverage permits:

- baseline lexical or current hybrid
- local `BAAI/bge-m3` hybrid when coverage exists
- heuristic rerank
- learned CrossEncoder rerank

Record:

- top-k result identifiers
- target rank movement
- latency
- GPU memory before/after learned rerank probe or smoke
- caveats around incomplete embedding coverage

### 4. Durable artifacts

- add or update benchmark JSONL fixtures only for stable, non-sensitive identifiers
- update this plan and the runbook with the observed decision

## Acceptance Criteria

- learned reranker smoke is either run successfully or explicitly deferred with reason
- at least three bounded query comparisons are recorded, unless data coverage blocks them
- GPU memory and latency observations are recorded
- the plan records a proceed/defer/swap decision
- roadmap and runbook are updated

## Validation Plan

- `slack-mirror search reranker-probe --smoke --json` or a documented non-smoke readiness probe
- targeted query comparison commands captured in this plan or runbook
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
