# Benchmark Fusion Experiment

State: CLOSED
Roadmap: P10
Opened: 2026-04-21
Closed: 2026-04-21

## Current State

- Corpus search already supports `weighted` and `rrf` fusion.
- CLI/API/MCP corpus search can pass the fusion method.
- `search profile-benchmark`, `search benchmark-diagnose`, and corpus-target `search health` currently evaluate only the default fusion path.
- `0084` showed that the current non-content fixture still misses most labeled targets in the top 10 even after BGE target coverage is fixed.
- The next safe experiment is to compare fusion methods over the same fixture without changing profile defaults or broadening rollout.

## Scope

- Thread an explicit fusion method through corpus benchmark evaluation.
- Add `--fusion weighted|rrf` to corpus-target benchmark commands:
  - `search health`
  - `search profile-benchmark`
  - `search benchmark-diagnose`
- Preserve `weighted` as the default.
- Record managed evidence comparing `weighted` and `rrf` on the non-content fixture.

## Non-Goals

- Do not change release defaults.
- Do not change retrieval-profile definitions.
- Do not tune weights or reranker behavior in this slice.
- Do not broaden BGE rollout.
- Do not expose message bodies in benchmark evidence.

## Acceptance Criteria

- Benchmark commands can evaluate corpus benchmarks with either `weighted` or `rrf`.
- Diagnostic JSON records which fusion method was used.
- Tests cover parser and evaluator plumbing.
- Live evidence shows whether `rrf` improves the current fixture versus `weighted`.

## Definition Of Done

- Plan, roadmap, and runbook are updated.
- Targeted tests pass.
- Generated docs are refreshed.
- Managed installed evidence is recorded.
- The next recommended semantic-search action is explicit.

## Result

- Threaded corpus fusion through benchmark evaluation:
  - `search health --fusion`
  - `search profile-benchmark --fusion`
  - `search benchmark-diagnose --fusion`
- Preserved `weighted` as the default.
- Fixed profile benchmark fidelity so corpus benchmarks now honor retrieval-profile lexical weight, semantic weight, and semantic scale, not only model/provider/rerank.
- Installed-wrapper weighted evidence on `default`:
  - `baseline`: hit@10 `0.333333`, nDCG@k `0.0789`, MRR@k `0.066667`, p95 `416.753 ms`
  - `local-bge-http`: hit@10 `0.333333`, nDCG@k `0.0789`, MRR@k `0.066667`, p95 `254.325 ms`
  - `local-bge-http-rerank`: hit@10 `0.222222`, nDCG@k `0.052758`, MRR@k `0.046296`, p95 `2049.439 ms`
- Installed-wrapper RRF evidence on `default`:
  - `baseline`: hit@10 `0.333333`, nDCG@k `0.0789`, MRR@k `0.066667`, p95 `503.048 ms`
  - `local-bge-http`: hit@10 `0.0`, nDCG@k `0.0`, MRR@k `0.0`, p95 `254.324 ms`
  - `local-bge-http-rerank`: hit@10 `0.222222`, nDCG@k `0.048231`, MRR@k `0.041667`, p95 `2038.287 ms`
- Diagnostic evidence:
  - weighted keeps `baseline` and `local-bge-http` tied at `4/19` target-label hits in the top 10
  - RRF drops `local-bge-http` to `0/19` target-label hits and makes rerank movement worse
- Interpretation:
  - RRF should not be promoted for this fixture
  - current BGE value remains latency, not relevance
  - the next relevance problem is not fusion policy; it is candidate generation/query formulation or corpus coverage beyond the three benchmark-labeled targets
- Next action:
  - add query formulation experiments that generate controlled alternate query strings per benchmark row and compare them with the same non-content diagnostics
