# Benchmark Target BGE Backfill

State: CLOSED
Roadmap: P10
Opened: 2026-04-21
Closed: 2026-04-21

## Current State

- `0081` added a non-content live relevance fixture and benchmark validation.
- The fixture has `19/19` labels resolved on `default`.
- The `baseline` model covers all fixture labels, but `local-bge-http` and `local-bge-http-rerank` cover `0/19`.
- Existing broad backfill commands can scan by channel/time or derived-text filters, but there is no narrow command that covers only benchmark-labeled targets.

## Scope

- Add a targeted benchmark-label embedding backfill path that reads a dataset and embeds only resolved relevant targets.
- Use existing sync-layer embedding storage helpers and retrieval-profile provider resolution.
- Support message labels now and derived-text labels through the same bounded target path if present.
- Validate the new command with unit tests and live managed evidence.
- Re-run benchmark validation and profile comparison after targeted BGE coverage.

## Non-Goals

- Do not broaden BGE rollout beyond benchmark-labeled targets.
- Do not change the release `baseline`.
- Do not publish private message bodies or snippets.
- Do not promote BGE or reranking in this slice.

## Acceptance Criteria

- A managed command can backfill embeddings for targets referenced by a benchmark dataset and retrieval profile.
- `search benchmark-validate` reports BGE coverage for the fixture after the targeted backfill.
- Profile benchmark evidence is recorded after coverage.
- Tests cover the target-only backfill path.

## Definition Of Done

- Plan, roadmap, and runbook are updated.
- Targeted tests pass.
- Generated docs are refreshed if CLI help changes.
- Managed command, validation, and profile benchmark evidence are recorded.
- The next recommended semantic-search action is explicit.

## Result

- Added `mirror benchmark-embeddings-backfill`, a bounded write command that:
  - reads benchmark JSONL labels
  - resolves labels through the shared app service
  - deduplicates message and derived-text targets
  - embeds only those targets for a selected retrieval profile
- Added sync helpers for target-only message embeddings and target-only derived-text chunk embeddings.
- Managed repo-env backfill evidence on `default` with `local-bge-http`:
  - labels: `19`
  - unique message targets: `3`
  - derived-text targets: `0`
  - message scanned: `3`
  - message embedded: `3`
  - skipped: `0`
  - missing: `0`
- Post-backfill validation:
  - `baseline`: `19/19` labels covered
  - `local-bge-http`: `19/19` labels covered
  - `local-bge-http-rerank`: `19/19` labels covered
- Post-coverage profile benchmark:
  - `baseline`: hit@3 `0.0`, hit@10 `0.333333`, nDCG@k `0.0789`, MRR@k `0.066667`, p95 `331.515 ms`
  - `local-bge-http`: hit@3 `0.0`, hit@10 `0.333333`, nDCG@k `0.0789`, MRR@k `0.066667`, p95 `245.402 ms`
  - `local-bge-http-rerank`: hit@3 `0.0`, hit@10 `0.222222`, nDCG@k `0.061032`, MRR@k `0.055556`, p95 `2128.806 ms`
- Installed-wrapper idempotence evidence:
  - labels: `19`
  - unique message targets: `3`
  - message embedded: `0`
  - skipped: `3`
  - missing: `0`
- Installed-wrapper profile benchmark:
  - `baseline`: hit@3 `0.0`, hit@10 `0.333333`, nDCG@k `0.0789`, MRR@k `0.066667`, p95 `608.239 ms`
  - `local-bge-http`: hit@3 `0.0`, hit@10 `0.333333`, nDCG@k `0.0789`, MRR@k `0.066667`, p95 `255.915 ms`
  - `local-bge-http-rerank`: hit@3 `0.0`, hit@10 `0.222222`, nDCG@k `0.061032`, MRR@k `0.055556`, p95 `2071.465 ms`
- Interpretation:
  - target coverage is no longer blocking this fixture
  - BGE still ties baseline on relevance for this fixture, though with lower p95 latency through the warm inference service
  - learned reranking remains worse and slower on this fixture
  - release `baseline` remains unchanged
- Next action:
  - add profile-aware query diagnostics with per-query rank movement and lane contribution summaries so the ranking failure can be diagnosed without dumping Slack message bodies
