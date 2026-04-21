# Non-Content Relevance Benchmark Pack

State: CLOSED
Roadmap: P10
Opened: 2026-04-21
Closed: 2026-04-21

## Current State

- `0080` added aggregate-safe multi-profile benchmark comparison.
- The existing `slack_smoke.jsonl` fixture is useful as a regression smoke check but not as a promotion gate.
- BGE coverage on the managed `default` workspace is still partial, so benchmark evidence must report whether labeled targets are covered by the profile model.
- Current benchmark datasets are JSONL files with `query` and `relevant` maps, but there is no repo-owned validation command that checks label resolvability or model coverage before running comparisons.

## Scope

- Add a read-only benchmark dataset validation/reporting command.
- Document the non-content benchmark fixture rules.
- Add a stronger live relevance fixture that uses stable IDs and query labels without message bodies.
- Run validation and profile comparison for `baseline`, `local-bge-http`, and `local-bge-http-rerank`.
- Keep the release `baseline` unchanged.

## Non-Goals

- Do not publish Slack message bodies or snippets.
- Do not broaden BGE rollout in this slice.
- Do not promote BGE or reranking based on partial coverage.
- Do not change benchmark thresholds for release checks.

## Acceptance Criteria

- A command can validate a benchmark dataset and report unresolved labels plus configured-model coverage for labeled message and derived-text targets.
- A new non-content live relevance fixture exists with broader query intent than the older three-query smoke file.
- Docs explain how to author and validate live benchmark fixtures without exposing private content.
- Managed validation and profile comparison evidence is recorded.

## Definition Of Done

- Plan, roadmap, and runbook are updated.
- Targeted unit tests pass.
- Generated docs are refreshed if CLI help changes.
- Managed validation/profile benchmark evidence is recorded.
- The next recommended semantic-search action is explicit.

## Result

- Added `search benchmark-validate`, a read-only benchmark dataset report that checks:
  - unresolved labels
  - ambiguous labels
  - per-profile configured-model coverage for labeled message and derived-text targets
- Added [docs/dev/benchmarks/README.md](/home/ecochran76/workspace.local/slack-export/docs/dev/benchmarks/README.md) with non-content fixture authoring rules.
- Added [slack_live_relevance_noncontent.jsonl](/home/ecochran76/workspace.local/slack-export/docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl), a nine-query live fixture with stable message labels and no message bodies.
- Managed validation evidence on `default`:
  - `9` queries
  - `19` labels
  - `19/19` labels resolved
  - unresolved labels: `0`
  - ambiguous labels: `0`
  - `baseline` model coverage: `19/19`
  - `local-bge-http` and `local-bge-http-rerank` model coverage: `0/19`
- Profile benchmark evidence on the same fixture:
  - `baseline`: hit@3 `0.0`, hit@10 `0.333333`, nDCG@k `0.0789`, MRR@k `0.066667`, p95 `332.812 ms`
  - `local-bge-http`: hit@3 `0.0`, hit@10 `0.333333`, nDCG@k `0.0789`, MRR@k `0.066667`, p95 `261.028 ms`
  - `local-bge-http-rerank`: hit@3 `0.0`, hit@10 `0.222222`, nDCG@k `0.061032`, MRR@k `0.055556`, p95 `2026.19 ms`
- Interpretation:
  - the new fixture is stronger than the old three-query smoke for regression tracking, but it is still not a BGE promotion gate until the labeled targets have BGE coverage
  - reranking remains experimental and should not be promoted
  - release `baseline` remains unchanged
- Next action:
  - add a narrow targeted BGE backfill path for benchmark labels or an equivalent operator command that can cover labeled targets without broad rollout
