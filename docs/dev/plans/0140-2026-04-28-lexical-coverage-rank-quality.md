# 0140 | Lexical coverage rank quality

State: CLOSED

Roadmap: P10

## Purpose

Improve remaining corpus benchmark rank quality by reducing lexical
over-ranking from repeated single-term hits when another row covers more of the
query intent.

## Current State

After `0139`, managed baseline corpus benchmarks have acceptable hit coverage:
hit@3 is `0.666667` and hit@10 is `1.0`. The remaining managed baseline
failure is low nDCG@k. Profile comparison after the row-level metric correction
shows `local-bge-http` is effectively tied with baseline on quality, while
`local-bge-http-rerank` is lower quality and slower. This makes baseline rank
quality the next bounded target.

The degraded query reports show rows with many repetitions of one lexical term
can outrank rows that cover more query concepts through exact terms, aliases, or
source labels. The current lexical ranker counts raw term occurrences, so a
single repeated word can dominate a more balanced candidate.

## Scope

- Add a bounded coverage-aware lexical scoring component.
- Preserve existing exact, alias, source-label, link, thread, and recency
  evidence paths.
- Keep candidate generation unchanged.
- Validate with a targeted unit test and managed live benchmark evidence.

## Non-goals

- Do not promote BGE or learned reranking.
- Do not change benchmark thresholds.
- Do not introduce fixture-specific target promotion.
- Do not alter MCP/API result contracts.

## Acceptance

- A candidate covering more distinct query concepts outranks a row that only
  repeats one term.
- Managed baseline benchmark evidence improves or at least does not regress
  hit@3, hit@10, nDCG@k, MRR@k, or p95 latency materially.
- Planning audit, targeted tests, `git diff --check`, and release check pass.

## Result

Implemented coverage-aware lexical scoring in `slack_mirror.search.keyword`.
The ranker now caps per-term repetition at two hits and adds a distinct query
concept coverage component across exact terms, alias groups, and non-generic
source-label matches. Candidate generation and result contracts are unchanged.

Managed `default` baseline evidence after the change:

- status: `pass_with_warnings`
- failure codes: none
- `hit_at_3`: `0.666667`
- `hit_at_10`: `1.0`
- `ndcg_at_k`: `0.602684`
- `mrr_at_k`: `0.60119`
- `latency_ms_p95`: `487.751`

Remaining warnings are attachment/OCR/query-degradation warnings, not benchmark
failure codes. BGE promotion is still not justified by this fixture:
`local-bge-http` remained effectively tied with baseline before this slice, and
`local-bge-http-rerank` remained lower quality and slower.
