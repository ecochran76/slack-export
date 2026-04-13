# API and MCP Contract

This document defines the minimal transport contract for the shipped local API and MCP surfaces.

It is not a full endpoint catalog. It captures the response shapes and semantics that callers can rely on across both transports.

## Scope

Current shared contract coverage:

- frontend auth
- runtime status
- live runtime validation
- runtime report listing
- corpus search
- search readiness
- search health
- outbound message sends
- outbound thread replies
- listener registration
- listener delivery listing
- listener delivery acknowledgement
- shared error envelope

The local HTTP API and MCP server are both thin wrappers over `slack_mirror.service.app`. When these contracts change, they should change together.

## Frontend Auth

API only:

- `GET /auth/status`
- `GET /auth/session`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /login`
- `GET /register`
- `GET /`

Current semantics:

- this is a bounded local-password baseline for browser-facing surfaces
- MCP has no equivalent today
- when frontend auth is enabled:
  - unauthenticated HTML requests for protected routes redirect to `/login`
  - unauthenticated protected JSON requests fail with `AUTH_REQUIRED`
- protected routes currently include:
  - `/`
  - `/exports/*`
  - `/v1/exports*`
  - `/runtime/reports*`
  - `/v1/runtime/reports*`
  - `/v1/runtime/status`
  - `/v1/runtime/live-validation`

Important fields for `/auth/status`:

- `enabled`
- `allow_registration`
- `cookie_name`
- `cookie_secure_mode`
- `session_days`
- `user_count`
- `registration_open`

Important fields for `/auth/session`, `/auth/register`, and `/auth/login`:

- `authenticated`
- `user_id`
- `username`
- `display_name`
- `session_id`
- `auth_source`
- `expires_at`

`/` is the canonical browser landing page when frontend auth is enabled. It is an HTML-only authenticated view over the existing runtime-status, runtime-report, and export-manifest surfaces.

## Runtime Reports

API:

- `GET /v1/runtime/reports`
- `GET /v1/runtime/reports/{name}`
- `GET /v1/runtime/reports/latest`
- `GET /runtime/reports`
- `GET /runtime/reports/{name}`
- `GET /runtime/reports/latest`
- `GET /runtime/reports/{name}.latest.html`
- `GET /runtime/reports/{name}.latest.md`
- `GET /runtime/reports/{name}.latest.json`

MCP:

- `runtime.report.latest`

Named report browsing remains API-only. MCP now exposes the freshest managed runtime report manifest for the common “latest snapshot” case.

Important fields for the JSON listing/detail routes:

- `name`
- `base_url`
- `fetched_at`
- `status`
- `summary`
- `html_url`
- `markdown_url`
- `json_url`

Important fields for `runtime.report.latest`:

- `ok`
- `report`
  - `name`
  - `base_url`
  - `fetched_at`
  - `status`
  - `summary`

`/runtime/reports/{name}` serves the latest HTML snapshot directly for human review.
`/runtime/reports` serves a simple HTML index over the currently available managed snapshots, with the freshest report highlighted and linked through `/runtime/reports/latest`, plus header links for the latest HTML and latest manifest.
`/runtime/reports/latest` serves the freshest available HTML snapshot regardless of its snapshot name, and `/v1/runtime/reports/latest` returns the matching manifest.

## Runtime Status

API:

- `GET /v1/runtime/status`

MCP:

- `runtime.status`

This is the lightweight managed-runtime status surface. It is intended for dashboards, probes, and operator scripts that need runtime artifact/service presence plus the latest persisted reconcile summary, without running the full live validation gate.

Important fields:

- `ok`
- `wrappers_present`
- `api_service_present`
- `config_present`
- `db_present`
- `cache_present`
- `rollback_snapshot_present`
- `services`
- `reconcile_workspaces`
  - `name`
  - `state_present`
  - `auth_mode`
  - `iso_utc`
  - `age_seconds`
  - `attempted`
  - `downloaded`
  - `warnings`
  - `failed`

## Live Validation

API:

- `GET /v1/runtime/live-validation`

MCP:

- `runtime.live_validation`

Both return the same shared validation payload with:

- `ok`
- `status`
  - `pass`
  - `pass_with_warnings`
  - `fail`
- `summary`
- `failure_count`
- `warning_count`
- `failure_codes`
- `warning_codes`
- `workspaces`
  - `name`
  - `event_errors`
  - `embedding_errors`
  - `event_pending`
  - `embedding_pending`
  - `stale_channels`
  - `stale_warning_suppressed`
  - `active_recent_channels`
  - `shell_like_zero_message_channels`
  - `unexpected_empty_channels`
  - `reconcile_state_present`
  - `reconcile_state_age_seconds`
  - `reconcile_auth_mode`
  - `reconcile_iso_utc`
  - `reconcile_attempted`
  - `reconcile_downloaded`
  - `reconcile_warnings`
  - `reconcile_failed`
  - `failure_codes`
  - `warning_codes`

Human-readable `lines` remain present for operators, but automation should prefer the structured fields above.

## Corpus Search

API:

- `GET /v1/workspaces/{workspace}/search/corpus`
- `GET /v1/search/corpus`

MCP:

- `search.corpus`

Both expose the same shared corpus-search result model over:

- messages
- attachment-derived text
- OCR-derived text

Important request fields:

- `query`
- `workspace`
  - required for workspace-scoped search unless `all_workspaces=true`
- `all_workspaces`
  - optional boolean for cross-workspace search through MCP or the top-level API route
- `mode`
  - `lexical`
  - `semantic`
  - `hybrid`
- `limit`
- `kind`
  - optional derived-text filter
- `source_kind`
  - optional derived-text source filter

Important result fields:

- `result_kind`
  - `message`
  - `derived_text`
- `text`
- `matched_text`
- `snippet_text`
- `chunk_index`
- `start_offset`
- `end_offset`
- `source_label`
- `workspace`
- `workspace_id`
- `_source`
  - `lexical`
  - `semantic`
  - `hybrid`
- `_lexical_score`
- `_semantic_score`
- `_hybrid_score`

Current semantics:

- lexical-first hybrid ranking is the shipped baseline
- message results reuse the existing message-search path
- derived-text results reuse shared-core `derived_text` rows
- long derived-text rows may be retrieved through chunk-level matches but still resolve to one owning derived-text result
- `matched_text` and `snippet_text` are best-match snippet fields for long documents and OCR-heavy attachments
- derived-text semantic scoring currently uses the same local embedding baseline used elsewhere in-repo
- cross-workspace corpus search is explicit rather than implicit:
  - CLI uses `--all-workspaces`
  - API uses `GET /v1/search/corpus`
  - MCP uses `all_workspaces=true`

## Search Readiness

API:

- `GET /v1/workspaces/{workspace}/search/readiness`

MCP:

- `search.readiness`

Both return one shared machine-readable readiness payload with:

- `workspace`
- `status`
  - `ready`
  - `degraded`
- `messages`
  - `count`
  - `embeddings`
    - `count`
    - `pending`
    - `errors`
- `derived_text`
  - `attachment_text`
    - `count`
    - `pending`
    - `errors`
    - `providers`
    - `jobs`
      - `pending`
      - `done`
      - `skipped`
      - `error`
    - `issue_reasons`
  - `ocr_text`
    - `count`
    - `pending`
    - `errors`
    - `providers`
    - `jobs`
      - `pending`
      - `done`
      - `skipped`
      - `error`
    - `issue_reasons`

Current semantics:

- this is a readiness summary, not a quality benchmark
- `degraded` currently means search corpus state exists but one or more tracked error conditions remain
- callers should prefer these structured counters over inferring readiness from ad hoc queue inspection
- provider coverage and issue-reason counts are intended for operator visibility and automation, not as a second quality gate separate from `search.health`

## Search Health

API:

- `GET /v1/workspaces/{workspace}/search/health`

MCP:

- `search.health`

Both return one shared health payload with:

- `workspace`
- `status`
  - `pass`
  - `pass_with_warnings`
  - `fail`
- `readiness`
  - the shared readiness payload
- `benchmark`
  - optional benchmark report when a dataset is provided
- `benchmark_thresholds`
- `extraction_thresholds`
- `degraded_queries`
- `failure_codes`
- `warning_codes`

Current benchmark gates:

- `BENCHMARK_HIT_AT_3_LOW`
- `BENCHMARK_HIT_AT_10_LOW`
- `BENCHMARK_NDCG_AT_K_LOW`
- `BENCHMARK_LATENCY_P95_HIGH`

Current extraction health gates:

- failures:
  - `ATTACHMENT_ERRORS_PRESENT`
  - `OCR_ERRORS_PRESENT`
- warnings:
  - `ATTACHMENT_PENDING_HIGH`
  - `OCR_PENDING_HIGH`
  - `ATTACHMENT_ISSUES_PRESENT`
  - `OCR_ISSUES_PRESENT`

Current semantics:

- health is a gate over readiness plus optional benchmark quality checks
- readiness degradation currently becomes a warning unless benchmark or extraction policy failures also occur
- benchmark output includes per-query diagnostics through `query_reports`
- `degraded_queries` surfaces the subset of benchmark queries that missed ranking-quality floors or hit-rate expectations
- benchmark execution is optional but should be used before ranking changes or release decisions that affect search behavior

## Outbound Write Success

API:

- `POST /v1/workspaces/{workspace}/messages`
- `POST /v1/workspaces/{workspace}/threads/{thread_ref}/replies`

MCP:

- `messages.send`
- `threads.reply`

Successful outbound actions return the normalized shared action shape. Important fields:

- `id`
- `workspace_id`
- `kind`
  - `message`
  - `thread_reply`
- `channel_id`
- `thread_ts`
- `status`
  - `pending`
  - `sent`
  - `failed`
- `idempotency_key`
- `options`
  - parsed from stored `options_json`
- `response`
  - parsed upstream Slack response when present
- `error`
- `idempotent_replay`
  - `false` for the first successful send/reply
  - `true` when the action was returned from an existing matching idempotency record
- `retryable`
  - `true` for `pending` and `failed`
  - `false` for `sent`

Semantics:

- callers should send an `idempotency_key` for any write they may retry
- repeated requests with the same workspace, action kind, and idempotency key return the existing action instead of sending a second Slack write
- idempotent replay is visible in the returned payload through `idempotent_replay`
- the result shape is the same whether the caller uses API or MCP

## Listener Registration

API:

- `POST /v1/workspaces/{workspace}/listeners`
- `GET /v1/workspaces/{workspace}/listeners`
- `GET /v1/workspaces/{workspace}/listeners/{listener_id}`
- `DELETE /v1/workspaces/{workspace}/listeners/{listener_id}`

MCP:

- `listeners.register`
- `listeners.list`
- `listeners.status`
- `listeners.unregister`

Listener registration is name-keyed within a workspace. Re-registering the same listener name updates the existing registration instead of creating a duplicate row.

Important listener fields:

- `id`
- `workspace_id`
- `name`
- `event_types_json`
- `channel_ids_json`
- `target`
- `delivery_mode`
- `enabled`
- `created_at`
- `updated_at`

Registration/filtering semantics:

- `name` is required
- `event_types` is optional
  - empty means all event types in the local listener model
- `channel_ids` is optional
  - empty means all channels
- both filters are conjunctive when present
  - event type must match if `event_types` is set
  - channel must match if `channel_ids` is set and the payload has a channel
- current default `delivery_mode` is `queue`

## Listener Deliveries

API:

- `GET /v1/workspaces/{workspace}/deliveries`
- `POST /v1/workspaces/{workspace}/deliveries/{delivery_id}/ack`

MCP:

- `deliveries.list`
- `deliveries.ack`

Delivery rows currently return these important fields:

- `id`
- `workspace_id`
- `listener_id`
- `event_type`
- `source_kind`
- `source_ref`
- `payload_json`
- `status`
- `attempts`
- `error`
- `delivered_at`
- `created_at`
- `updated_at`

Current delivery status model:

- `pending`
- `delivered`
- `failed`

Acknowledgement semantics:

- `deliveries.ack` / `POST .../ack` updates exactly one existing delivery row in the addressed workspace
- default ack status is `delivered`
- callers may also set `status` explicitly, including `failed`
- `attempts` increments on every acknowledgement write
- `delivered_at` is set on acknowledgement, including failed acknowledgements
- `error` may be attached to record consumer failure detail

Consumer guidance:

- use `status=pending` polling for queue-like consumption
- ack with `delivered` only after the subscribed process has accepted the delivery
- ack with `failed` plus `error` when the consumer handled the delivery attempt but could not complete downstream work
- treat `payload_json` as the canonical event payload body for the delivery row

## Error Envelope

API errors return:

```json
{
  "ok": false,
  "error": {
    "code": "INVALID_ARGUMENT",
    "message": "channel_ref is required",
    "retryable": false,
    "details": {
      "operation": "messages.send",
      "workspace": "default"
    }
  }
}
```

MCP errors return the same machine-readable envelope in JSON-RPC `error.data`:

```json
{
  "error": {
    "code": -32602,
    "message": "channel_ref is required",
    "data": {
      "code": "INVALID_ARGUMENT",
      "message": "channel_ref is required",
      "retryable": false,
      "details": {
        "tool": "messages.send"
      }
    }
  }
}
```

Stable shared fields:

- `code`
- `message`
- `retryable`
- `details`

Current stable service error codes include:

- `INVALID_ARGUMENT`
- `INVALID_REQUEST`
- `NOT_FOUND`
- `AMBIGUOUS_TARGET`
- `AUTH_CONFIGURATION_ERROR`
- `UPSTREAM_ERROR`
- `METHOD_NOT_FOUND`
- `INTERNAL_ERROR`

## Caller Guidance

- Prefer structured fields over parsing human-readable text.
- Treat `retryable` as transport guidance, not a guarantee that an immediate retry is safe under all product conditions.
- Use idempotency keys for write actions whenever retries, agent loops, or network retries are possible.
- For live health, key off `status`, `failure_codes`, and per-workspace queue fields rather than the freeform `summary`.
