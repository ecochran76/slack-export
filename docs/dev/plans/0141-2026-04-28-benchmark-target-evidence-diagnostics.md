# 0141 | Benchmark target evidence diagnostics

State: CLOSED

Roadmap: P10

## Purpose

Make residual benchmark degradation easier to classify by adding non-content
target-evidence metadata to `search benchmark-diagnose`.

## Current State

After `0140`, the managed baseline non-content relevance benchmark passes with
warnings and no failure codes. The remaining degraded queries are concentrated
in paraphrase-like cases such as `nylon polymer synthesis`, `monomer materials
discussion`, and `nylon formulation notes`.

Manual inspection shows some top results are genuinely relevant to the literal
query, while some expected targets are curated/contextual rows whose relevance
is not fully represented by exact query terms in the target message body. The
current diagnostic command reports ranks and compact result explanations, but
it does not summarize how much query evidence exists inside each expected
target. That makes it too easy to keep tuning ranking against fixture ambiguity.

## Scope

- Add compact, non-content evidence metadata for expected benchmark targets.
- Report exact/source-label coverage counts without exposing message bodies.
- Preserve `--include-text` as the only path that emits content.
- Keep retrieval, ranking, benchmark thresholds, and dataset format unchanged.

## Non-goals

- Do not add more ranking heuristics in this slice.
- Do not change benchmark relevance labels.
- Do not promote BGE or rerank profiles.
- Do not add a new CLI command.

## Acceptance

- `benchmark-diagnose` expected targets include evidence metadata.
- The default JSON output remains non-content.
- Tests cover message target evidence without requiring text output.
- Planning audit, targeted tests, `git diff --check`, release check, and a
  managed diagnostic smoke pass.

## Result

`search benchmark-diagnose` now attaches an `evidence` object to expected
targets in both query-level `expected_targets` and per-profile target reports.
The evidence is non-content and reports:

- normalized query terms
- resolved/text target counts
- exact query terms present in the target text
- query terms present in the target source label
- missing query terms
- exact and source-label coverage ratios

Managed `default` diagnostic evidence for the residual degraded queries showed:

- `nylon polymer synthesis`: both expected targets contain `nylon` and
  `polymer`, but not `synthesis`
- `monomer materials discussion`: both expected targets contain `monomer` and
  `materials`, but not `discussion`
- `nylon formulation notes`: expected targets contain `nylon`, but not
  `formulation` or `notes`

This supports treating the remaining degraded rows as fixture/context or richer
semantic-query work, not as another immediate baseline ranker tweak.
