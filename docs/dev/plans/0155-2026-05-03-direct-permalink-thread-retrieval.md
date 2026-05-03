# Plan 0155 | Direct Permalink Thread Retrieval

State: CLOSED

Roadmap: P12

## Current State

Slack Mirror can discover conversations, search scoped corpus results, build
selected-result context packs, and open context windows from known message
`action_target` ids. A SoyLei website handoff exposed a gap: when an operator
provides a direct Slack permalink, agents still have to manually parse the URL,
guess the workspace, run bounded message-list fallbacks, and filter locally for
the thread timestamp.

This slice is now shipped. Slack Mirror has shared application-service
permalink resolution and thread retrieval with CLI, API, and MCP wrappers.
The resolver supports exact configured workspace domains plus a safe unique
legacy fallback for older configs where a Slack host such as
`soyleiinnovations.slack.com` only has a configured workspace name such as
`soylei`.

## Scope

- Parse Slack archive permalinks into workspace domain, channel id, message
  timestamp, and thread-root timestamp.
- Resolve the permalink workspace against configured/mirrored workspace names
  and domains.
- Return mirrored-message status and a ready-to-use thread/context action
  target.
- Add a first-class thread getter that returns the thread root and replies in
  chronological order with safe sender labels, text, native ids, action
  targets, and file metadata where available.
- Expose the shared application-service behavior through CLI, API, and MCP.
- Update agent-facing Slack Mirror search skill guidance so URL workflows start
  with permalink resolution, not semantic search or browser Slack.

## Non-Goals

- Do not call live Slack APIs to hydrate missing permalink targets in this
  slice.
- Do not move Slack web authentication into the agent workflow.
- Do not change Receipts or sibling repo behavior.
- Do not redesign context-window or selected-result export contracts.

## Acceptance Criteria

- Given a permalink such as
  `https://soyleiinnovations.slack.com/archives/C06L8DVBWQP/p1777774228756839?thread_ts=1777682271.668819&cid=C06L8DVBWQP`,
  the resolver returns `soylei`, `C06L8DVBWQP`, message timestamp
  `1777774228.756839`, and thread timestamp `1777682271.668819`.
- The thread getter returns root plus replies from mirrored SQLite state
  without using browser Slack.
- MCP exposes a one-call `thread.from_permalink` workflow for agents.
- CLI/API expose equivalent resolver and thread-get surfaces for debugging and
  non-MCP clients.
- Tests cover permalink parsing, workspace resolution, thread projection, API,
  and MCP tool behavior.

## Definition Of Done

- Shared service tests pass for permalink and thread retrieval.
- API and MCP targeted tests pass.
- Planning wiring audit passes.
- `git diff --check` passes.

## Shipped Surface

- CLI:
  - `slack-mirror-user messages permalink-resolve <slack-url> --json`
  - `slack-mirror-user messages thread --workspace <ws> --channel <channel_id> --thread-ts <ts> --selected-ts <ts> --json`
- API:
  - `GET /v1/permalink/resolve?url=<slack-url>`
  - `GET /v1/workspaces/{workspace}/threads/{channel_id}/{thread_ts}`
- MCP:
  - `permalink.resolve`
  - `thread.get`
  - `thread.from_permalink`
