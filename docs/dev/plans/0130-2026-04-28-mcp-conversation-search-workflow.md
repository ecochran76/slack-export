# 0130 | MCP conversation search workflow

State: CLOSED

Roadmap: P11

## Purpose

Reduce agent error when moving from conversation discovery to selected-result
context by exposing a narrow MCP workflow helper that scopes search to the
selected Slack conversation and returns ready-to-expand action targets.

## Current State

`conversations.list` can discover MPDM, IM, private-channel, and public-channel
candidates. `search.corpus` can already honor message-lane `in:<channel>`
operators, and `search.context_pack` / `search.context_export` already expand
selected `action_target` values. Agents still had to manually stitch those
pieces together and could easily search too broadly or forget the exact next
tool payload.

## Scope

- Add MCP `search.conversation` as a helper over existing service boundaries.
- Accept either an explicit `workspace` + `channel_id` or discovery filters
  compatible with `conversations.list`.
- Run scoped corpus search using `in:<channel_id>`.
- Return only rows whose message `action_target` belongs to the selected
  conversation.
- Return `action_targets` plus explicit `search.context_pack` and
  `search.context_export` next-call payloads.

## Non-goals

- Do not add a new API route or CLI command.
- Do not add a new export format.
- Do not change the underlying search ranking model.
- Do not make derived-text attachment hits conversation-scoped until the
  derived-text lane has a first-class channel provenance filter.

## Acceptance

- MCP tool list includes `search.conversation`.
- The helper calls `conversations.list` when discovery filters are used.
- The helper calls `search.corpus` with an `in:<channel_id>` scoped query.
- Results are filtered back to the selected conversation's channel id.
- The response includes ready-to-use context-pack/export argument payloads.
- Targeted tests, compile check, planning audit, `git diff --check`, and a live
  managed-wrapper smoke pass.

## Status

CLOSED. MCP now exposes `search.conversation` as an agent-friendly bridge from
conversation discovery to scoped search and selected-result context/export.
