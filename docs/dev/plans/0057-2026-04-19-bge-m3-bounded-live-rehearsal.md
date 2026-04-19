# BGE-M3 Bounded Live Rehearsal

State: CLOSED
Roadmap: P10
Opened: 2026-04-19

## Scope

Run a bounded quality rehearsal of the `BAAI/bge-m3` message-semantic path on real mirrored data without widening the rollout to the whole live corpus.

This plan covers:

- a temporary rehearsal DB derived from the live mirror
- bounded channel-scoped `bge-m3` message embedding backfill
- side-by-side semantic query checks against the current baseline on known paraphrase targets
- recording the rehearsal outcome in roadmap/runbook state

This plan does not include:

- broad live-db `bge-m3` backfill
- derived-text chunk embeddings
- learned reranking
- ANN or vector-database changes

## Current State

- `0055` landed provider-routed message embeddings with optional `sentence_transformers`
- `0056` validated that the workstation can run `BAAI/bge-m3` on the RTX 5080 after installing the optional `local-semantic` extra
- the next unanswered product question is whether the stronger local model materially improves the known weak paraphrase queries on real mirrored data

## Target Outcome

After this slice:

- the repo has one bounded live-data rehearsal of `bge-m3` message retrieval quality
- the rehearsal uses a temp DB or equivalently isolated path, not the live production DB
- the result is explicit enough to guide the next semantic-search slice

## Outcome

This slice is complete.

What was rehearsed:

- temporary DB copy derived from the live mirror
- temporary config pointing that DB at:
  - `search.semantic.model: BAAI/bge-m3`
  - `search.semantic.provider.type: sentence_transformers`
  - `device: cuda`
- bounded channel-scoped `bge-m3` backfill for:
  - `default` target channel
  - `soylei` target DM
  - `pcg` target DM

Bounded backfill size:

- `default`: `886` messages
- `soylei`: `1815` messages
- `pcg`: `1568` messages
- total: `4269` messages

Observed outcome:

- current `local-hash-128` baseline missed all three known paraphrase targets in this bounded rehearsal:
  - `hit@3 = 0`
  - `hit@10 = 0`
  - `ndcg@k = 0`
- `BAAI/bge-m3` improved all three:
  - `default`: direct fix, `hit@3 = 1`, `mrr = 1.0`, `ndcg = 1.0`
  - `soylei`: partial fix, `hit@3 = 1`, `mrr = 0.333333`, `ndcg = 0.5`
  - `pcg`: strong fix, `hit@3 = 1`, `mrr = 1.0`, `ndcg = 0.787155`

Interpretation:

- the stronger local message-semantic path is good enough to justify a broader bounded rollout for messages
- the next slice should focus on making `bge-m3` backfill and evaluation usable beyond this hand-picked rehearsal, not on revisiting whether the model family is viable

## Acceptance Criteria

- bounded live rehearsal completes without mutating the live production DB
- at least one known paraphrase target is evaluated in each current live workspace:
  - `default`
  - `soylei`
  - `pcg`
- the outcome clearly records whether `bge-m3` improves semantic retrieval enough to justify a broader bounded rollout

## Validation Plan

- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- runtime rehearsal:
  - bounded temporary DB copy
  - bounded channel-scoped `bge-m3` embedding pass
  - side-by-side semantic query comparison against the baseline
