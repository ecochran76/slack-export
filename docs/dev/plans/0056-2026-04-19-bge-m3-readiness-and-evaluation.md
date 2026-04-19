# BGE-M3 Readiness And Evaluation

State: CLOSED
Roadmap: P10
Opened: 2026-04-19

## Scope

Make the stronger local message-semantic path measurable and safe to rehearse on the actual workstation before broader rollout.

This plan covers:

- repo-owned readiness probing for the configured semantic provider
- GPU and local runtime visibility for the optional `sentence_transformers` path
- making the existing benchmark path use the configured message embedding provider instead of silently bypassing it
- optional dependency declaration for local semantic model work

This plan does not include:

- derived-text chunk embeddings
- learned reranking
- ANN or vector-database changes
- making heavy ML dependencies mandatory for default installs

## Current State

- `0055` landed the provider-routed message embedding path and optional `sentence_transformers` support
- the workstation has a real NVIDIA GPU available, but the repo env does not yet ship local semantic model dependencies by default
- the existing search benchmark tooling was written before the provider seam and can still bypass the configured message embedding provider

## Target Outcome

After this slice:

- operators can probe the configured message embedding provider and see whether local semantic runtime requirements are actually present
- the benchmark and health path exercise the configured provider when evaluating semantic search quality
- the repo has an explicit optional dependency group for local semantic experimentation
- the RTX 5080 workstation can be assessed with a repo-owned command before attempting a full `bge-m3` model rehearsal

## Outcome

This slice is complete.

Landed:

- optional `local-semantic` dependency declaration in `pyproject.toml`
- repo-owned semantic provider probing through:
  - `slack-mirror search provider-probe`
- runtime probing for the optional `sentence_transformers` path, including:
  - package presence
  - torch CUDA visibility
  - detected CUDA device names
  - optional `nvidia-smi` memory visibility
  - optional embed smoke execution
- search readiness now reports provider probe details without forcing a heavy model load
- the benchmark path now threads the configured message embedding provider through corpus evaluation instead of silently bypassing it
- `scripts/eval_search.py` can now resolve the configured provider through `--config`

Observed local workstation result:

- NVIDIA GeForce RTX 5080 visible
- CUDA available through torch after installing the optional extra
- `BAAI/bge-m3` smoke succeeded on `cuda`

Kept intentionally out of scope:

- derived-text chunk embeddings
- learned reranking
- forced always-on model preload in the service layer
- broad live-database `bge-m3` backfill or search-quality rollout

## Acceptance Criteria

- a repo-owned CLI probe exists for configured semantic provider readiness
- the probe surfaces GPU/runtime information relevant to the optional `sentence_transformers` path
- search benchmark execution uses the configured message embedding provider
- optional local semantic dependencies are declared without becoming baseline install requirements
- roadmap, runbook, and docs are updated in the same slice

## Validation Plan

- targeted tests:
  - `uv run python -m unittest tests.test_embeddings tests.test_app_service tests.test_cli -v`
- compile check:
  - `python -m py_compile slack_mirror/search/embeddings.py slack_mirror/search/eval.py slack_mirror/service/app.py slack_mirror/cli/main.py scripts/eval_search.py tests/test_embeddings.py tests/test_app_service.py tests/test_cli.py`
- runtime probe:
  - `uv run slack-mirror search provider-probe --json`
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
