# Live Relevance Benchmark Lock

State: CLOSED
Roadmap: P10
Opened: 2026-04-20
Closed: 2026-04-20

## Current State

- `0079` proved warm local BGE embedding and reranking through the loopback inference service.
- `baseline`, `local-bge-http`, and `local-bge-http-rerank` are now usable profile names.
- Existing benchmark fixtures include both synthetic corpus/derived-text fixtures and one older real-message fixture (`slack_smoke.jsonl`).
- BGE coverage is still partial, so benchmark interpretation must separate model quality from rollout coverage.

## Scope

- Add an aggregate-safe profile benchmark command if the existing single-profile health output is too verbose for release evidence.
- Compare `baseline`, `local-bge-http`, and `local-bge-http-rerank` on bounded real-query benchmark checks.
- Record aggregate relevance and latency evidence without publishing private Slack message bodies.
- Decide whether existing fixtures are sufficient for the next release gate or whether a new non-content fixture should be added.
- Keep the release `baseline` unchanged.

## Non-Goals

- Do not broaden BGE rollout in this slice.
- Do not publish private message text in docs or handoff.
- Do not promote `local-bge-http` or `local-bge-http-rerank` as default profiles.
- Do not change ranking thresholds unless live evidence justifies a narrow update.

## Acceptance Criteria

- Managed benchmark runs compare all three target profiles on at least one real-query fixture.
- Results are summarized in roadmap/runbook without private message contents.
- If fixture drift is found, the next action is explicit.
- Planning audit and targeted validation pass.

## Definition Of Done

- Plan, roadmap, and runbook are updated.
- Managed benchmark evidence is recorded.
- Targeted validation passes.
- The next recommended semantic-search action is explicit.

## Result

- Added `search profile-benchmark` as a read-only aggregate-safe comparator over named retrieval profiles.
- The command reuses the existing `search health` benchmark evaluator and omits per-query reports unless `--include-details` is set.
- Managed live benchmark evidence on `default` using `docs/dev/benchmarks/slack_smoke.jsonl`:
  - `baseline`: `3` queries, hit@3 `0.0`, hit@10 `0.666667`, nDCG@k `0.197161`, MRR@k `0.116667`, p95 `234.801 ms`, degraded query count `3`
  - `local-bge-http`: `3` queries, hit@3 `0.0`, hit@10 `0.666667`, nDCG@k `0.197161`, MRR@k `0.116667`, p95 `276.353 ms`, degraded query count `3`
  - `local-bge-http-rerank`: `3` queries, hit@3 `0.0`, hit@10 `0.333333`, nDCG@k `0.143559`, MRR@k `0.083333`, p95 `906.816 ms`, degraded query count `3`
- Interpretation:
  - the existing real-query fixture is still useful as a regression smoke check
  - it is not sufficient as a promotion gate because relevance remains low and the BGE rollout remains partial
  - learned reranking did not improve this fixture and should remain experimental
  - the release default remains `baseline`
- Next action:
  - build a stronger benchmark pack with non-content labels, broader query intents, and explicit message/derived-text coverage before promoting BGE or learned reranking
