# 0135 | Source-label candidate generation

State: CLOSED

Roadmap: P10

## Purpose

Improve candidate generation for source-oriented search queries without
changing the release-default retrieval profile or relying on another
ranking-only experiment.

## Current State

Post-`v0.2.0` benchmark evidence showed all benchmark labels are resolvable and
covered for the `baseline` profile, but hit rates remain poor. The miss table
showed source lookup queries such as `research website nylon` were failing
because plain lexical terms matched only message text; channel/source labels
were display metadata and did not contribute to candidate generation unless the
operator used explicit `channel:`/`source:` syntax.

## Scope

- Keep the primary FTS-backed lexical path text-first and fast.
- Add a bounded source-label fallback only when a plain query term matches a
  mirrored channel id or channel name.
- Let fallback candidates satisfy channel-label terms with channel id/name and
  non-label terms with message text.
- Score channel-label term hits alongside text term hits.
- Validate against the existing non-content benchmark fixture.

## Non-goals

- Do not change retrieval-profile defaults.
- Do not promote BGE or reranker profiles.
- Do not alter semantic vector storage or backfill behavior.
- Do not add new query syntax.

## Acceptance

- Existing keyword-search tests pass.
- Source-label terms can retrieve a message in a matching channel even when the
  label term is not present in message text.
- Managed baseline benchmark shows no latency regression and records whether
  relevance improved.
- Planning audit and `git diff --check` pass.

## Status

CLOSED. Baseline benchmark evidence improved from hit@10 `0.333333` to
`0.555556` and hit@3 `0.0` to `0.111111`, with p95 latency `437.746 ms`.
The benchmark still fails thresholds, so the next P10 slice should target the
remaining paraphrase/candidate-generation misses rather than treating this as a
complete relevance fix.
