# 0139 | Benchmark row-level metrics

State: CLOSED

Roadmap: P10

## Purpose

Correct corpus benchmark aggregate metrics so hit@k, nDCG, and MRR evaluate
result rows rather than flattened label aliases.

## Current State

After `0138`, `benchmark-diagnose` reports row ranks and shows hit@10 is close
to acceptable, but `profile-benchmark` still computes metrics from a flattened
list of label alternatives. For Slack message rows, each result can contribute
both `channel_id:ts` and `channel_name:ts`, so a target on the third result row
can be counted as a label position beyond 3. This makes hit@3 and rank-quality
metrics misleading and inconsistent with the row-level diagnostic command.

## Scope

- Update corpus benchmark evaluation to score each result row once.
- Let each result row match any of its stable label alternatives.
- Preserve existing top-result label output for compatibility.
- Keep retrieval, ranking, and result ordering unchanged.
- Validate against targeted unit tests plus the live non-content benchmark.

## Non-goals

- Do not change search ranking.
- Do not change benchmark-diagnose output.
- Do not change benchmark fixture format.
- Do not change release thresholds in this slice.

## Acceptance

- Unit tests prove a third result row with an alternate label counts as hit@3.
- Managed baseline benchmark evidence records the metric movement after the
  correction.
- Planning audit and `git diff --check` pass.

## Result

Implemented row-level corpus benchmark scoring in `slack_mirror.search.eval`.
Each result row now contributes one relevance value by matching any stable label
alternative for that row, while the existing flattened `top_results` labels are
preserved for report compatibility.

Managed `default` baseline evidence after the correction:

- `hit_at_3`: `0.666667`
- `hit_at_10`: `1.0`
- `ndcg_at_k`: `0.526822`
- `mrr_at_k`: `0.504762`
- `latency_ms_p95`: `435.95`
- remaining failure code: `BENCHMARK_NDCG_AT_K_LOW`

The correction aligns `profile-benchmark` aggregate metrics with
`benchmark-diagnose` row ranks. It does not change retrieval, ranking, result
ordering, or release thresholds.
