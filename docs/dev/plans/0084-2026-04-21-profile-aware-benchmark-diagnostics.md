# Profile-Aware Benchmark Diagnostics

State: CLOSED
Roadmap: P10
Opened: 2026-04-21
Closed: 2026-04-21

## Current State

- `search profile-benchmark` compares aggregate relevance metrics across named retrieval profiles.
- `search benchmark-validate` verifies label resolvability and profile-model coverage before interpreting relevance metrics.
- `mirror benchmark-embeddings-backfill` can now cover only benchmark-labeled targets for a selected profile.
- The current non-content live fixture has full BGE target coverage, but `baseline` and `local-bge-http` still tie on relevance while `local-bge-http-rerank` is worse.
- Per-result corpus search already exposes `_explain` metadata with source lane, lane ranks, weighted/semantic scores, fusion method, weights, and rerank metadata.
- There is no benchmark-level diagnostic command that shows expected target ranks, profile-to-profile movement, and lane contribution summaries without exposing Slack message bodies.

## Scope

- Add a read-only benchmark diagnostic command for corpus benchmarks.
- Compare named retrieval profiles on each dataset query.
- Resolve expected labels through the existing benchmark label resolver.
- Report expected target rank, hit window, top result labels, and compact score/rank/explain metadata.
- Summarize rank movement against the first profile as baseline.
- Keep default output non-content: labels, ranks, metrics, result kinds, channel/source identifiers, and explain metadata only.
- Provide an explicit opt-in flag if snippets/text are ever needed for local debugging.

## Non-Goals

- Do not change ranking, fusion, weights, or retrieval-profile defaults.
- Do not promote BGE or reranking.
- Do not broaden BGE rollout.
- Do not emit private Slack message bodies by default.
- Do not add frontend or MCP surfaces in this slice.

## Acceptance Criteria

- Operators can run one command to diagnose the current non-content benchmark fixture across `baseline`, `local-bge-http`, and `local-bge-http-rerank`.
- JSON output identifies unresolved labels, expected target ranks per profile, and rank movement versus the baseline profile.
- Default output remains safe for runbook evidence because it omits message bodies and snippets.
- Tests cover the service diagnostic payload and CLI parser.

## Definition Of Done

- Plan, roadmap, and runbook are updated.
- Targeted tests pass.
- Generated docs are refreshed if CLI help changes.
- Live installed diagnostic evidence is recorded against the managed `default` fixture.
- The next recommended semantic-search action is explicit.

## Result

- Added `search benchmark-diagnose`, a read-only corpus benchmark diagnostic command that compares target ranks across named retrieval profiles.
- Default output is non-content:
  - stable result labels
  - target ranks and hit windows
  - profile movement versus the first profile
  - top result labels
  - source counts
  - compact `_explain` metadata for score/rank/lane contribution
- Added explicit `--include-text` for local-only debugging when message bodies or snippets are safe to inspect.
- Added service and CLI parser tests.
- Updated README, config docs, benchmark docs, and generated CLI/man docs.
- Installed-wrapper diagnostic evidence on `default` with the non-content fixture:
  - `baseline`: `4/19` target-label hits in top 10, ranks `[5, 8, 2, 2]`, movement `unchanged=4`, `missing_both=15`
  - `local-bge-http`: `4/19` target-label hits in top 10, ranks `[5, 8, 2, 2]`, movement `unchanged=4`, `missing_both=15`
  - `local-bge-http-rerank`: `4/19` target-label hits in top 10, ranks `[6, 8, 3, 2]`, movement `worse=2`, `unchanged=2`, `missing_both=15`
  - default diagnostic JSON had `include_text=false` and no `text` or `snippet_text` keys
- Interpretation:
  - the relevance problem is not target coverage anymore
  - BGE is not moving expected targets versus baseline on this fixture
  - reranking demotes half of the visible hits and should remain experimental
  - most labeled targets are absent from the top 10 for every current profile
- Next action:
  - tune the retrieval pipeline with diagnostics-first changes, starting with query formulation or fusion experiments over the same fixture before any broader rollout
