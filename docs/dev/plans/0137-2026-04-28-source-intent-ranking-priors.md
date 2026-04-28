# 0137 | Project-language ranking priors

State: CLOSED

Roadmap: P10

## Purpose

Improve the remaining source/topic benchmark misses with narrow
project-language candidate aliases, without widening the public query syntax.

## Current State

After `0136`, the non-content benchmark improved to hit@10 `0.777778` and
hit@3 `0.222222`. The remaining misses are no longer broad candidate-generation
failures. They include queries such as `REU nylon project` and
`nylon formulation notes`, where relevant messages use project/program or
working-with language rather than the exact query token.

## Scope

- Keep explicit operators such as `source:` and `channel:` unchanged.
- Add narrow aliases for project/notes/formulation language only where current
  benchmark evidence shows matching corpus vocabulary.
- Preserve exact/original term ranking priority over alias-only matches.
- Validate against the same non-content benchmark fixture.

## Non-goals

- Do not add user-visible query syntax.
- Do not introduce a configurable synonym editor.
- Do not change retrieval-profile defaults or semantic provider behavior.
- Do not weaken explicit negative terms or structured filters.

## Acceptance

- Unit tests cover project-language alias fallback.
- Managed baseline benchmark evidence records hit/latency movement.
- Planning audit and `git diff --check` pass.

## Status

CLOSED. The committed implementation adds narrow project/formulation aliases
and treats non-generic channel/source-label hits as stronger ranking evidence.
Generic label terms such as `research`, `project`, and `source` are deliberately
excluded from the channel-label boost after an initial experiment showed they
could over-promote unrelated topic channels.

Managed baseline benchmark evidence held hit@10 at `0.777778` and hit@3 at
`0.222222`, while improving nDCG@k from `0.222312` to `0.253767`. p95 latency
was `450.851 ms`. Compact diagnosis showed `REU nylon project` now ranks
`reu2022:1652305847.089769` at rank 3 while preserving the earlier
`nylon research` hits.

The remaining quality problem is not solved by more small lexical aliases.
Remaining misses include `website:1658780875.573539` for broad research/source
queries and `reu2022:1652305847.089769` for `nylon formulation notes`; the next
slice should inspect corpus grouping, duplicate suppression, and benchmark
target/source priors before adding more aliases.
