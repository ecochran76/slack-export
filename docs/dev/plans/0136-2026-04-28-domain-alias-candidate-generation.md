# 0136 | Domain-alias candidate generation

State: CLOSED

Roadmap: P10

## Purpose

Improve message lexical candidate generation for narrow domain-language
paraphrases in the live relevance benchmark without changing retrieval-profile
defaults or promoting a learned reranker.

## Current State

The source-label fallback from `0135` improved source lookup queries, but the
same non-content benchmark still misses several targets whose Slack text uses
nearby domain vocabulary. Examples include benchmark queries such as
`polyamide monomers`, `nylon polymer synthesis`, `monomer materials discussion`,
and `nylon formulation notes`, while relevant messages contain terms such as
`polyamides`, `comonomers`, `polymer chemistry design`, `materials`, and
`Nylon 59 properties`.

## Scope

- Add a small built-in domain alias map for candidate generation only.
- Keep the primary FTS-backed lexical path unchanged and text-first.
- Run a bounded fallback only when plain positive query terms have known
  aliases.
- Require every positive query term to be satisfied by either the original term
  or one of its aliases.
- Score alias hits lower than original-term hits so exact textual matches keep
  ranking priority.
- Validate against the existing non-content benchmark fixture.

## Non-goals

- Do not add new query syntax.
- Do not alter semantic vector storage, BGE rollout behavior, or provider
  configuration.
- Do not change retrieval-profile defaults.
- Do not add a user-editable synonym system in this slice.

## Acceptance

- Unit tests prove alias-backed candidate generation works for domain
  paraphrases.
- Unit tests prove original-term hits outrank alias-only hits.
- Managed baseline benchmark evidence records whether hit rate improved and
  whether latency stayed acceptable.
- Planning audit and `git diff --check` pass.

## Status

CLOSED. The implementation keeps the primary FTS path unchanged and adds a
bounded FTS-indexed alias fallback for a deliberately small built-in domain
alias map. Exact/original term hits keep priority because alias hits are
scored at lower weight and capped per query term.

Managed baseline benchmark evidence improved hit@10 from `0.555556` to
`0.777778`, hit@3 from `0.111111` to `0.222222`, nDCG@k from `0.160233` to
`0.222312`, and MRR@k from `0.131481` to `0.214815`. p95 latency was
`477.057 ms`, above the prior `0135` run but below the benchmark latency
failure threshold.

The benchmark still fails quality thresholds. Remaining misses include
`website:1658780875.573539` for `nylon research` and `polyamide research
source`, `reu2022:1652305847.089769` for `REU nylon project` and
`nylon formulation notes`, and broader source/topic combinations that need a
ranking and source-prior pass rather than more alias expansion.
