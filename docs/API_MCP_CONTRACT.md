# API and MCP Contract

This document defines the minimal transport contract for the shipped local API and MCP surfaces.

It is not a full endpoint catalog. It captures the response shapes and semantics that callers can rely on across both transports.

## Scope

Current shared contract coverage:

- frontend auth
- runtime status
- live runtime validation
- runtime report listing
- runtime report CRUD
- export CRUD
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

## MCP Initialize

The MCP stdio server now negotiates the caller's requested `initialize.params.protocolVersion`
when it is one of the repo-supported protocol versions. Today the supported set is:

- `2024-11-05`
- `2025-03-26`
- `2025-06-18`

If the caller omits `protocolVersion` or requests an unsupported value, the server falls back to
the current default `2025-03-26`.

For handshake debugging, the MCP server also supports opt-in tracing:

- `SLACK_MIRROR_MCP_TRACE=1`
- optional `SLACK_MIRROR_MCP_TRACE_FILE=/absolute/path/to/trace.jsonl`

When enabled, the server emits one JSON object per line for:

- process startup
- frame read and write boundaries
- `initialize` request details, including requested and negotiated protocol version
- early `tools/list` and `tools/call` dispatch, including tool-call failures

If `SLACK_MIRROR_MCP_TRACE_FILE` is unset, trace lines go to stderr.

## MCP Release Baseline

The first stable user-scoped release treats MCP as a supported local operator interface when it is reached through the managed launcher:

```bash
~/.local/bin/slack-mirror-mcp
```

Before adding MCP clients such as Codex, OpenClaw, or another agent runtime, use these gates:

```bash
slack-mirror-user user-env status --json
slack-mirror-user user-env check-live --json
slack-mirror release check --require-managed-runtime --json
```

The managed-runtime checks verify the MCP wrapper with a real stdio health request and a bounded concurrent readiness probe. A passing single process does not replace `check-live` when multiple clients will be configured.

MCP clients should reconnect after `slack-mirror user-env update` or `slack-mirror-user user-env update`. Long-lived clients keep the tool schema and server code they loaded at process start.

The managed runtime status probes are safe for agent-client environments that do not inherit the normal interactive shell DBus variables. The service rehydrates the user runtime and bus environment before calling `systemctl --user`, so `runtime.status` and `runtime.live_validation` should not report every unit inactive solely because `XDG_RUNTIME_DIR` or `DBUS_SESSION_BUS_ADDRESS` was missing at client launch.

Supported release-baseline MCP tool groups:

- runtime and install health: `health`, `runtime.status`, `runtime.live_validation`, `runtime.report.latest`, `workspaces.list`, `workspace.status`
- search and retrieval diagnostics: `search.corpus`, `search.readiness`, `search.health`, `search.profiles`, `search.semantic_readiness`
- outbound actions: `messages.send`, `threads.reply`
- listener workflow: `listeners.register`, `listeners.list`, `listeners.status`, `listeners.unregister`, `deliveries.list`, `deliveries.ack`

Recommended operator preflight from MCP clients:

- call `health` to confirm the stdio server is responsive
- call `runtime.status` to read managed artifact, service, MCP smoke, and concurrent-MCP readiness state
- call `runtime.live_validation` when the client needs stricter workspace, token, queue, DB, and live-unit health
- call `workspace.status` before workspace-scoped search or outbound actions
- call `search.readiness` or `search.semantic_readiness` before assuming semantic coverage is complete

Outbound tools are real writes. Use them only after workspace token verification, and prefer an `options.idempotency_key` for retryable sends. `messages.send` accepts channel references or DM-style targets according to the shared outbound service contract; `threads.reply` requires an existing channel reference and thread timestamp/reference.

Listener tools are for agent-consumable event delivery. Register a listener with `listeners.register`, inspect it with `listeners.status`, poll work with `deliveries.list`, and acknowledge completion or failure with `deliveries.ack`.

First-release MCP non-goals:

- tenant onboarding, manifest generation, Slack credential installation, and live-service installation remain CLI/browser workflows
- frontend auth, password/session management, and browser user provisioning remain API/browser/CLI workflows
- named runtime-report browsing, runtime-report CRUD, export CRUD, and HTML/PDF/DOCX export generation remain API/browser/CLI workflows
- heavy semantic rollout, BGE backfill, and reranker rollout remain explicit CLI/operator work rather than automatic MCP side effects

MCP tool failures use JSON-RPC `error` responses. The `error.data` value contains the shared service error envelope so clients can branch on stable fields instead of parsing prose.

## Frontend Auth

API only:

- `GET /auth/status`
- `GET /auth/session`
- `GET /auth/sessions`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/sessions/{id}/revoke`
- `GET /login`
- `GET /register`
- `GET /`
- `GET /settings`
- `GET /search`

Current semantics:

- this is a bounded local-password baseline for browser-facing surfaces
- MCP has no equivalent today
- when frontend auth is enabled:
  - unauthenticated HTML requests for protected routes redirect to `/login`
  - unauthenticated protected JSON requests fail with `AUTH_REQUIRED`
- `POST /auth/register`, `POST /auth/login`, and `POST /auth/logout` require a same-origin `Origin` or `Referer` header and fail with `CSRF_FAILED` otherwise
- `POST /auth/sessions/{id}/revoke` follows the same same-origin browser rule and only operates on sessions owned by the authenticated user
- `POST /auth/login` is subject to a bounded failed-login throttle and returns `429 RATE_LIMITED` with retry metadata when the configured threshold is exceeded
- protected routes currently include:
  - `/`
  - `/exports/*`
  - `/v1/exports*`
  - `/search`
  - `/runtime/reports*`
  - `/v1/runtime/reports*`
  - `/v1/runtime/status`
  - `/v1/runtime/live-validation`

Important fields for `/auth/status`:

- `enabled`
- `allow_registration`
- `registration_allowlist`
- `registration_allowlist_count`
- `registration_mode`
- `cookie_name`
- `cookie_secure_mode`
- `session_days`
- `session_idle_timeout_seconds`
- `login_attempt_window_seconds`
- `login_attempt_max_failures`
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

Important fields for `/auth/sessions`:

- `session_id`
- `auth_source`
- `created_at`
- `last_seen_at`
- `expires_at`
- `revoked_at`
- `active`
- `expired`
- `idle_expired`

`/` is the canonical browser landing page when frontend auth is enabled. It is an HTML-only authenticated view over the existing runtime-status, runtime-report, and export-manifest surfaces.

`/settings` is the browser-facing account/settings page for the same frontend-auth seam. It is an authenticated HTML view over:

- current frontend-auth policy
- registration allowlist state
- auth-governance policy such as session lifetime, idle timeout, and login-throttle settings
- current-user browser sessions
- revoke actions backed by `POST /auth/sessions/{id}/revoke`

`/search` is the authenticated browser search page for the shipped corpus-search contract. It currently provides:

- workspace-scoped or all-workspace corpus search over the existing API routes
- browser controls for search mode, result limit, derived-text kind, and derived-text source kind
- bounded previous/next pagination backed by the same `limit` and `offset` API parameters
- page-position and result-range display backed by API `total` counts
- browser-visible workspace readiness context when searching one workspace
- URL-backed search state so the current browser query can be reloaded or shared
- stable JSON detail destinations for message and derived-text hits, backed by repo-owned API routes rather than a second browser viewer contract

`/register` remains the browser registration entrypoint, and now surfaces any configured frontend-auth registration allowlist directly in the page copy.

`/login` now uses the same identity language and labels the sign-in field as `Email or username`.

## Runtime Reports

API:

- `GET /v1/runtime/reports`
- `GET /v1/runtime/reports/{name}`
- `GET /v1/runtime/reports/latest`
- `POST /v1/runtime/reports`
- `POST /v1/runtime/reports/{name}/rename`
- `DELETE /v1/runtime/reports/{name}`
- `GET /runtime/reports`
- `GET /runtime/reports/{name}`
- `GET /runtime/reports/latest`
- `GET /runtime/reports/{name}.latest.html`
- `GET /runtime/reports/{name}.latest.md`
- `GET /runtime/reports/{name}.latest.json`

Browser manager behavior on `/runtime/reports`:

- report creation uses configured publish-origin choices instead of a raw base-URL text field
- the page exposes guided name presets plus a timestamped default
- rename is an inline row action, not a prompt dialog
- successful report rename and delete now update the page inline instead of forcing a full reload

Browser manager behavior on `/exports`:

- workspace and channel choices come from the existing mirrored-state API, not raw free-text entry
- the page now includes browser-side channel filtering for larger workspaces
- filtering stays bounded to the already-loaded valid channel list and does not introduce a separate search contract
- export rename is now an inline row action instead of a prompt dialog
- successful export rename and delete now update the page inline instead of forcing a full reload

MCP:

- `runtime.report.latest`

Named report browsing remains API-only. MCP now exposes the freshest managed runtime report manifest for the common “latest snapshot” case.

Important fields for the JSON listing/detail routes:

- `schema_version`
- `generated_at`
- `producer`
  - `name`
  - `version`
- `provenance`
  - `runtime_status_source`
  - `live_validation_source`
- `name`
- `base_url`
- `fetched_at`
- `status`
- `summary`
- `validation`
  - `status`
  - `summary`
  - `failure_count`
  - `warning_count`
  - `failure_codes`
  - `warning_codes`
  - `workspace_count`
- `html_url`
- `markdown_url`
- `json_url`

Create semantics for `POST /v1/runtime/reports`:

- request fields:
  - `base_url`
  - `name`
  - optional `timeout`
- response:
  - `ok`
  - `report`

Update semantics for `POST /v1/runtime/reports/{name}/rename`:

- bounded to rename only
- request fields:
  - `name`
- response:
  - `ok`
  - `report`

Delete semantics for `DELETE /v1/runtime/reports/{name}`:

- response:
  - `ok`
  - `deleted`
  - `name`

Important fields for `runtime.report.latest`:

- `ok`
- `report`
  - `schema_version`
  - `generated_at`
  - `producer`
  - `provenance`
  - `name`
  - `base_url`
  - `fetched_at`
  - `status`
  - `summary`
  - `validation`

`/runtime/reports/{name}` serves the latest HTML snapshot directly for human review.
`/runtime/reports` now serves a browser management page over the currently available managed snapshots, with the freshest report highlighted and linked through `/runtime/reports/latest`, plus bounded create/rename/delete controls backed by the same runtime-report CRUD API routes. Successful create, rename, and delete mutations now update the page inline instead of forcing a full page reload.
`/runtime/reports/latest` serves the freshest available HTML snapshot regardless of its snapshot name, and `/v1/runtime/reports/latest` returns the matching manifest.

## Exports

API:

- `GET /v1/workspaces/{workspace}/channels`
- `GET /v1/exports`
- `GET /v1/exports/{export_id}`
- `POST /v1/exports`
- `POST /v1/exports/{export_id}/rename`
- `DELETE /v1/exports/{export_id}`
- `GET /exports/{export_id}`
- `GET /exports/{export_id}/{filepath}`
- `GET /exports/{export_id}/{filepath}/preview`

Current semantics:

- `GET /v1/workspaces/{workspace}/channels` provides valid mirrored channel choices for the browser export picker
- `POST /v1/exports` is intentionally bounded to `kind=channel-day`
- export updates are intentionally bounded to rename only
- the API remains a thin wrapper over the existing managed bundle ownership in `slack_mirror.exports`

Important fields for export listing/detail routes:

- `schema_version`
- `generated_at`
- `producer`
  - `name`
  - `version`
- `provenance`
  - `metadata_source`
  - `url_contract_source`
- `export_id`
- `kind`
- `workspace`
- `channel`
- `channel_id`
- `day`
- `default_audience`
- `bundle_urls`
- `bundle_url`
- `file_count`
- `attachment_count`
- `files`
  - `relpath`
  - `role`
  - `content_type`
  - `size_bytes`
  - `download_urls`
  - `preview_urls`
  - `download_url`
  - `preview_url`

Important fields for `GET /v1/workspaces/{workspace}/channels`:

- `channel_id`
- `name`
- `channel_class`
- `message_count`
- `latest_message_ts`
- `latest_message_day`

Create semantics for `POST /v1/exports`:

- request fields:
  - `kind`
  - `workspace`
  - `channel`
  - `day`
  - optional `tz`
  - optional `audience`
  - optional `export_id`
- response:
  - `ok`
  - `export`

Update semantics for `POST /v1/exports/{export_id}/rename`:

- bounded to rename only
- request fields:
  - `export_id`
  - optional `audience`
- response:
  - `ok`
  - `export`

Delete semantics for `DELETE /v1/exports/{export_id}`:

- response:
  - `ok`
  - `deleted`
  - `export_id`

`/exports` now serves a browser management page over the managed export bundles, with bounded channel-day create plus rename/delete controls backed by the same export CRUD API routes. The create form now uses dependent workspace/channel selectors populated from `/v1/workspaces/{workspace}/channels` instead of raw free-text channel entry, and successful create/rename/delete mutations update the page inline instead of forcing a full page reload.

## Runtime Status

API:

- `GET /v1/runtime/status`

MCP:

- `runtime.status`

This is the lightweight managed-runtime status surface. It is intended for dashboards, probes, and operator scripts that need runtime artifact/service presence plus the latest persisted reconcile summary, without running the full live validation gate.

Important fields:

- `ok`
- `wrappers_present`
- `mcp_ready`
- `mcp_multi_client_ready`
- `mcp_smoke_error`
- `mcp_multi_client_error`
- `mcp_multi_client_clients`
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

Current semantics:

- `wrappers_present` means the managed wrapper launchers are present on disk
- `mcp_ready` means the managed `slack-mirror-mcp` wrapper successfully answered a real MCP health request over stdio
- `mcp_smoke_error` carries the latest wrapper-probe failure detail when `mcp_ready` is false
- `mcp_multi_client_ready` means the managed `slack-mirror-mcp` wrapper passed a bounded concurrent readiness probe across multiple simultaneous wrapper launches
- `mcp_multi_client_error` carries the latest concurrent-probe failure detail when `mcp_multi_client_ready` is false
- `mcp_multi_client_clients` records how many simultaneous wrapper launches were used for the bounded concurrent probe

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
- `GET /v1/workspaces/{workspace}/messages/{channel_id}/{ts}`
- `GET /v1/workspaces/{workspace}/derived-text/{source_kind}/{source_id}?kind={derivation_kind}`
- `GET /v1/workspaces/{workspace}/derived-text/{source_kind}/{source_id}?kind={derivation_kind}&extractor={extractor}`

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
- `offset`
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
- `action_target`
- `_source`
  - `lexical`
  - `semantic`
  - `hybrid`
- `_lexical_score`
- `_semantic_score`
- `_hybrid_score`
- `_explain`

`action_target` is the stable selection contract for downstream workflows. It is additive to the display-oriented row fields and should be preferred by API, MCP, browser, and agent clients that need to stage search hits for later export, reporting, or actions.

Message action targets include:

- `version`
- `kind: message`
- `id`
- `workspace`
- `workspace_id`
- `channel_id`
- `channel_name`
- `ts`
- `thread_ts`
- `user_id`
- `selection_label`

Derived-text action targets include:

- `version`
- `kind: derived_text`
- `id`
- `workspace`
- `workspace_id`
- `derived_text_id`
- `source_kind`
- `source_id`
- `source_label`
- `derivation_kind`
- `extractor`
- `chunk_index`
- `start_offset`
- `end_offset`
- `selection_label`

Current semantics:

- lexical-first hybrid ranking is the shipped baseline
- message results reuse the existing message-search path
- derived-text results reuse shared-core `derived_text` rows
- long derived-text rows may be retrieved through chunk-level matches but still resolve to one owning derived-text result
- `matched_text` and `snippet_text` are best-match snippet fields for long documents and OCR-heavy attachments
- selected search candidates should be persisted or handed off using `action_target`, not by scraping labels, snippets, or score fields
- derived-text semantic scoring currently uses the same local embedding baseline used elsewhere in-repo
- cross-workspace corpus search is explicit rather than implicit:
  - CLI uses `--all-workspaces`
  - API uses `GET /v1/search/corpus`
  - MCP uses `all_workspaces=true`
- pagination is bounded and offset-based:
  - API routes accept `limit` plus `offset`
  - the current browser page uses previous/next controls over that same contract
  - the current API also exposes `total` so browser clients can render page and range metadata without inventing a second paging contract
- the browser uses the read-only message and derived-text detail routes as stronger result destinations without adding a second browser-native viewer contract

Detail route semantics:

- message detail returns one repo-owned message envelope with:
  - workspace
  - channel metadata
  - user label
  - thread metadata
  - stored message fields
  - parsed `raw_json` payload under `message`
- derived-text detail returns one repo-owned derived-text envelope with:
  - workspace
  - source and derivation metadata
  - stored derived-text fields
  - parsed `metadata`
  - chunk rows under `chunks`

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
