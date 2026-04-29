# 0138 | Corpus source-diversity ordering

State: CLOSED

Roadmap: P10

## Purpose

Improve first-page corpus search density by interleaving repeated results from
the same source/channel after scoring, without changing message-level lexical
scores or retrieval-profile defaults.

## Current State

After `0137`, the baseline benchmark still fails quality thresholds even though
hit@10 is improved. Compact diagnosis shows several top-10 result windows are
cluttered by repeated rows from the same source, especially
`oc-dev-slack-export`, while expected targets from other sources are already in
the candidate pool just below duplicate-heavy rows. A dry-run source-diversity
simulation showed `website` moves into the top 10 for `nylon research` and
`reu2022` moves to rank 2 for `REU nylon project`.

## Scope

- Add corpus-level source-diversified ordering after lexical/semantic/hybrid
  scoring.
- Preserve each row's original score and explanation metadata.
- Do not drop duplicate-source rows; only interleave them behind first results
  from other sources.
- Leave message-level search ranking unchanged.
- Validate against the same non-content benchmark fixture.

## Non-goals

- Do not add another alias or synonym expansion.
- Do not change retrieval-profile defaults or semantic providers.
- Do not add a new CLI/API/MCP option in this slice.
- Do not apply hard per-source caps that hide results.

## Acceptance

- Unit tests prove corpus search interleaves repeated-source rows without
  dropping them.
- Managed baseline benchmark evidence records hit/rank/latency movement.
- Planning audit and `git diff --check` pass.

## Status

CLOSED. Corpus search now applies source-diversified ordering after scoring for
lexical, semantic, hybrid, and multi-workspace result sets. The implementation
does not mutate per-row lexical/semantic/hybrid scores and does not hide
duplicate-source rows; it interleaves first results from distinct sources before
returning later rows from already-seen sources.

Managed baseline benchmark evidence improved hit@10 from `0.777778` to
`0.888889`, nDCG@k from `0.253767` to `0.286554`, MRR@k from `0.214815` to
`0.244444`, and p95 latency from `450.851 ms` to `438.661 ms`. Hit@3 held at
`0.222222`.

Compact diagnosis showed:
- `nylon research` now includes `website:1658780875.573539` at rank 10
- `polyamide monomers` now includes `website:1658780875.573539` at rank 10
- `research website nylon` moved `website:1658780875.573539` from rank 3 to
  rank 2
- `REU nylon project` moved `reu2022:1652305847.089769` from rank 3 to rank 2
  and `general:1645631573.091969` from rank 4 to rank 3
- `monomer materials discussion` moved `reu2022:1652305847.089769` from rank 9
  to rank 7

The benchmark still fails hit@3 and nDCG thresholds. Remaining misses now
require either better target-specific semantic retrieval or explicit grouped
source/result presentation, not another default lexical alias.
