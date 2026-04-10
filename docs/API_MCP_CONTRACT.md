# API and MCP Contract

This document defines the minimal transport contract for the shipped local API and MCP surfaces.

It is not a full endpoint catalog. It captures the response shapes and semantics that callers can rely on across both transports.

## Scope

Current shared contract coverage:

- live runtime validation
- outbound message sends
- outbound thread replies
- shared error envelope

The local HTTP API and MCP server are both thin wrappers over `slack_mirror.service.app`. When these contracts change, they should change together.

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
  - `failure_codes`
  - `warning_codes`

Human-readable `lines` remain present for operators, but automation should prefer the structured fields above.

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
