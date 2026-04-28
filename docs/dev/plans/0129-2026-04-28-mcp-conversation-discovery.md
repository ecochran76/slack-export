# 0129 | MCP conversation discovery

State: CLOSED

Roadmap: P11

## Purpose

Make agent-led review workflows less dependent on prior daily summaries or
manual filesystem inspection by exposing a narrow read-only MCP conversation
discovery surface.

## Current State

Slack Mirror already has mirrored channel, member, user, and message state in
SQLite. MCP can search corpus results and expand selected action targets, but
agents did not have a compact way to discover likely MPDM/private-channel
candidates by workspace, conversation type, display name, or member label.

## Scope

- Add a shared application-service method for read-only conversation discovery.
- Add an MCP `conversations.list` tool with filters for:
  - workspace or all workspaces
  - conversation type: public channel, private channel, IM, or MPDM
  - channel/display-name query
  - member-label query, with conversation name/id fallback when membership rows
    are sparse
  - bounded limit
- Return compact metadata only: workspace, channel id/name/type, message count,
  latest timestamp, and member labels where available.
- Document the MCP tool and the intended workflow with existing
  `search.corpus`, `search.context_pack`, and `search.context_export`.

## Non-goals

- Do not expose raw message bodies through conversation discovery.
- Do not add a new export format or report renderer.
- Do not change channel sync or membership persistence semantics.
- Do not replace selected-result context/export workflows.

## Acceptance

- MCP tool list includes `conversations.list`.
- The tool calls the shared service method with the expected filters.
- The service can filter MPDM rows by member label and return message/latest
  metadata.
- Targeted tests, planning audit, and `git diff --check` pass.
- A live managed-wrapper smoke can discover real MPDM candidates.

## Status

CLOSED. `conversations.list` is available through MCP and backed by the shared
application service.
