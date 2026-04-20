# 0064 | Semantic Retrieval Profiles And Rollout Controls

State: CLOSED

Roadmap: P10

## Current State

- The repo has a provider seam for message and derived-text embeddings.
- The repo has bounded message and derived-text chunk embedding backfill commands.
- The repo has an opt-in reranker provider seam, including an experimental local learned reranker.
- The shipped default remains `local-hash-128` with no reranking.
- Operators currently have to manually align model ids, provider config, rerank config, and backfill commands.

## Scope

- Add named retrieval profiles that bundle retrieval mode, embedding model/provider, weights, and reranker intent.
- Keep existing default search behavior unchanged unless a profile is explicitly selected.
- Add CLI profile listing and profile selection for corpus search.
- Add read-only tenant rollout planning that reports current model coverage and the exact bounded backfill/probe commands to run.
- Document the profile contract and operator loop.

## Non-Goals

- Do not promote the learned reranker to default behavior.
- Do not run heavy backfills automatically.
- Do not redesign the browser search UI in this slice.
- Do not require API/MCP/frontend readiness surfacing in this slice; that remains follow-up work.

## Acceptance Criteria

- `slack-mirror search profiles` lists builtin and configured retrieval profiles.
- `slack-mirror search corpus --retrieval-profile <name>` applies the profile model/provider/mode/rerank defaults while explicit CLI flags still override search parameters.
- `slack-mirror mirror rollout-plan --workspace <name> --retrieval-profile <name>` reports current message and derived-text embedding coverage for the profile model.
- The rollout plan emits copyable bounded commands for provider probe, message embedding backfill, derived-text embedding backfill, reranker probe when applicable, and search-health verification.
- Docs describe baseline, local semantic, and local semantic plus reranker profiles.

## Definition Of Done

- Code, docs, generated CLI reference, roadmap, and runbook are updated.
- Targeted tests cover profile resolution, CLI parsing, and rollout-plan service output.
- Planning audit passes.

## Closure Notes

- Added builtin retrieval profiles for `baseline`, `local-bge`, and experimental `local-bge-rerank`.
- Added config override support under `search.retrieval_profiles`.
- Added `search profiles`.
- Added `--retrieval-profile` to corpus search, provider probe, reranker probe, message embedding backfill, and derived-text chunk embedding backfill.
- Added `mirror rollout-plan` as a read-only coverage and command-planning surface for tenant semantic rollout.
- Kept default search behavior unchanged unless a profile is explicitly selected.
