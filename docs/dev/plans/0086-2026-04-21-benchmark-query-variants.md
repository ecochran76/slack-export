# 0086 | Benchmark Query Variants

State: CLOSED
Roadmap: P10
Opened: 2026-04-21
Closed: 2026-04-21

## Current State

- `search profile-benchmark` compares named retrieval profiles and fusion methods at aggregate level.
- `search benchmark-diagnose` explains target rank movement without exposing Slack content by default.
- Recent evidence shows BGE ties the local-hash baseline under weighted fusion, RRF is worse, and most benchmark targets are missing from the top 10 across current profiles.
- The next likely relevance bottleneck is query formulation or candidate generation, not provider rollout or fusion policy.

## Scope

- Add a read-only benchmark command that evaluates deterministic query rewrites against the same JSONL benchmark dataset.
- Keep output aggregate-safe by default and non-content even when per-query details are requested.
- Compare variants across named retrieval profiles using the existing profile/model/provider/rerank/fusion wiring.
- Support authored dataset variants for future fixtures without requiring a production ranking change.

## Non-Goals

- Do not change default search ranking, tokenization, query parsing, or fusion behavior.
- Do not introduce learned query expansion or external LLM rewriting in this slice.
- Do not expose Slack message bodies or derived-text snippets in the default diagnostic output.

## Acceptance Criteria

- A CLI command such as `slack-mirror search benchmark-query-variants` exists.
- The command reports per-profile/per-variant benchmark metrics and identifies the best observed variant by relevance metric.
- The command supports deterministic variants such as original, lowercase, dehyphenated, and alphanumeric-normalized query forms.
- The command supports explicit benchmark-row `query_variants` values when present.
- Unit tests cover parser wiring and one variant that improves lexical matching without changing production search behavior.
- README, config docs, benchmark docs, generated CLI docs, and generated manpage are updated.
- Live managed-wrapper evidence is collected against the non-content benchmark dataset before any follow-up ranking recommendation.

## Definition Of Done

- Tests and generated-doc checks pass.
- Planning audit passes.
- Managed release check passes or records only expected non-blocking warnings.
- Evidence is recorded in `RUNBOOK.md`.
- The slice is closed or an explicit follow-up remains open.

## Outcome

- `search benchmark-query-variants` now compares deterministic query rewrites across named retrieval profiles.
- Default output remains aggregate-only and non-content.
- `--include-details` exposes only per-query stable result labels, not message bodies or snippets.
- Live evidence on the current non-content fixture shows lowercase ties original relevance, `alnum` slightly lowers rank quality, and `dehyphen` is worse.
- No query-normalization promotion is justified from this fixture; the next relevance work should target candidate generation or query grammar/operator semantics rather than automatic punctuation rewriting.
