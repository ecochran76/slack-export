# Default Search Backlog Drain

State: CLOSED
Roadmap: P10
Opened: 2026-04-20
Closed: 2026-04-20

## Scope

Drain the release-baseline search backlog on the managed `default` workspace and rerun readiness/search-health smoke.

This slice covers:

- inspect pending embedding and derived-text queues before work
- process the one known pending `default` embedding job if still present
- process pending `default` derived-text jobs in bounded passes
- rerun readiness, semantic-readiness, and search-health checks after processing
- record whether benchmark failures remain after queue cleanup

This slice does not include:

- broad file reconciliation or Slack API backfill
- installing optional BGE/reranker dependencies
- changing release retrieval defaults
- fixing benchmark quality failures unless they are directly caused by queue backlog

## Current State

- `0073` found `default` passed search health with warnings because attachment-text and OCR derived-text jobs were pending.
- `0074` added MCP/API retrieval-profile corpus search and refreshed the managed install.
- The release baseline remains `baseline` / `local-hash-128`.
- Before processing, `default` had complete message embedding coverage (`91,572/91,572`) and no pending message embeddings.
- Before processing, `default` had derived-text backlog:
  - attachment text jobs: `99` pending
  - OCR text jobs: `45` pending
- The bounded processors completed the backlog without job errors:
  - attachment text: `99` jobs inspected, `52` processed, `47` skipped as unsupported media, `0` errored
  - OCR text: `45` jobs inspected, `32` processed, `13` skipped, `0` errored
- Processing created derived-text chunks and revealed attachment chunk embedding coverage was incomplete for the configured baseline model:
  - attachment chunks: `11,100` total, `3,242` already embedded, `7,858` missing
  - OCR chunks: `42` total, `42` embedded
- `derived-text-embeddings-backfill --retrieval-profile baseline --kind attachment_text` embedded the missing `7,858` attachment chunks.
- Final MCP readiness for `default` is `ready` for the release baseline:
  - messages: `91,572/91,572` embedded with `local-hash-128`
  - derived-text chunks: `11,142/11,142` embedded with `local-hash-128`
  - attachment-text jobs: `0` pending, `0` errors, `47` unsupported-media skips
  - OCR-text jobs: `0` pending, `0` errors, skips classified as `ocr_no_text_detected` and `pdf_has_text_layer`
- Final no-dataset `search.health` is `pass_with_warnings` with only extraction issue warnings:
  - `ATTACHMENT_ISSUES_PRESENT`
  - `OCR_ISSUES_PRESENT`
- `local-bge` and `local-bge-rerank` remain unavailable in the managed install because optional `sentence_transformers` and `torch` dependencies are not installed there.
- Benchmark quality remains poor after backlog cleanup:
  - derived-text semantic smoke: `hit_at_3=0.0`, `hit_at_10=0.0`, `ndcg_at_k=0.0`, `p95=1100.941 ms`
  - corpus hybrid smoke: `hit_at_3=0.0`, `hit_at_10=0.0`, `ndcg_at_k=0.0`, `p95=54561.510 ms`
  - corpus hybrid depth: `hit_at_3=0.0`, `hit_at_10=0.0`, `ndcg_at_k=0.0`, `p95=54690.619 ms`
- The remaining benchmark failures are ranking and performance failures of the `local-hash-128` release baseline, not queue backlog failures.

## Acceptance Criteria

- before/after queue counts are recorded: met.
- pending `default` embedding jobs are processed or explained: met; none were pending for messages, and missing derived-text chunk embeddings were backfilled.
- pending `default` derived-text jobs are processed or remaining failures are classified: met.
- no-dataset `search.health --workspace default` is rerun: met through MCP `search.health`, returning `pass_with_warnings`.
- benchmark `search.health` checks are rerun enough to determine whether queue cleanup changed failure shape: met; readiness is now complete but benchmark relevance and latency still fail.

## Validation Plan

- MCP `search.readiness` for `workspace=default`
- `slack-mirror-user search semantic-readiness --workspace default --json`
- `slack-mirror-user search health --workspace default --json`
- targeted derived-text and corpus benchmark checks after queue processing
- `uv run slack-mirror release check --require-managed-runtime --json`
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Implementation Notes

- The derived-text processors were launched in parallel during this slice and completed cleanly. Future operational runs should prefer serial processing per workspace because both jobs write the same workspace database.
- The non-existent `slack-mirror-user search readiness` CLI command was replaced by the MCP `search.readiness` tool surface and CLI `search health` checks.
- Backlog cleanup did not change the release default retrieval profile. `baseline` remains the first-release default.
- The failed benchmark results should feed the next semantic-quality slice: real local embeddings, faster candidate retrieval, and profile-aware benchmark promotion.
