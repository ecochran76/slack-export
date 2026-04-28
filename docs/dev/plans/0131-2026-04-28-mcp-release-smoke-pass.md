# 0131 | MCP release smoke pass

State: CLOSED

Roadmap: P11

## Purpose

Run and record a full managed-runtime MCP smoke pass after the conversation
discovery and conversation-search workflow helpers landed.

## Current State

The managed runtime already validates the MCP launcher with single-client and
bounded concurrent readiness probes. MCP now also has the release-baseline
search, conversation discovery, scoped conversation search, context-pack,
runtime, workspace, and listener tools expected for the first stable
user-scoped release. The remaining need for this slice was evidence that the
installed managed wrapper can exercise that surface together.

## Scope

- Run `slack-mirror-user user-env status --json`.
- Run `slack-mirror-user user-env check-live --json`.
- Run `slack-mirror release check --require-managed-runtime --json`.
- Exercise the managed `~/.local/bin/slack-mirror-mcp` wrapper over stdio:
  - initialization and tool listing
  - runtime/status/report tools
  - workspace status and workspace listing
  - conversation discovery and scoped conversation search
  - corpus search and context-pack expansion
  - search profiles, readiness, semantic readiness, and search health
  - listener register/status/delivery-list/unregister lifecycle
- Avoid real Slack outbound writes during this smoke pass.

## Non-goals

- Do not send Slack messages or thread replies.
- Do not create durable selected-result exports.
- Do not cut a release tag.
- Do not change MCP tool behavior in this slice.

## Acceptance

- Managed status and live validation pass.
- Release check passes with no failures.
- The full MCP stdio smoke passes with no JSON-RPC errors.
- Any remaining release warnings are documented.

## Status

CLOSED. Managed `check-live` passed cleanly after a transient embedding-backlog
warning drained. `release check --require-managed-runtime --json` passed with
only the expected development-version warning. The MCP stdio smoke passed across
the release-baseline read and listener surfaces; real outbound writes were
intentionally skipped.
