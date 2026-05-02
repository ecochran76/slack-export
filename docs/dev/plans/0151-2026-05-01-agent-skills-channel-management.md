# 0151 | Agent Skills Channel Management

State: CLOSED

Roadmap: P11

## Current State

- Slack Mirror exposes MCP and API outbound message writes, conversation discovery, search, listeners, and runtime checks.
- Repo-bundled agent skills cover send/search/ingest/live-ops/export workflows.
- Slack app manifests already include channel-write scopes, but Slack Mirror does not yet expose a shared service/API/MCP channel-management operation.

## Goal

Add a guarded channel-management workflow so agents can satisfy requests such as:

> Please create a channel on the SoyLei tenant called `<channel>`. Make it private and invite Baker and Michael.

## Scope

- Add shared Slack API helpers for conversation create and invite.
- Add one service operation for create-or-reuse channel plus invitees.
- Expose the operation through:
  - API: `POST /v1/workspaces/{workspace}/channels`
  - MCP: `channels.create`
- Add a repo-bundled `slack-mirror-channel-management` skill and route it from the orchestrator.
- Document channel-management semantics in the API/MCP contract and agent-skill docs.
- Install updated skills into the local agent runtimes.

## Guardrails

- Resolve named invitees before creating a new Slack channel.
- Normalize human channel names to Slack-compatible lowercase names.
- Reuse an already mirrored same-name channel when privacy is compatible.
- Refuse to reuse a public channel for a private-channel request or vice versa.
- Treat channel creation and invites as real Slack mutations; no live channel creation should be run in validation without explicit user approval.

## Validation

- Targeted service/API/MCP unit tests for channel create/invite.
- Skill frontmatter and installer smoke.
- Planning audit and `git diff --check`.
- Installed runtime refresh and local API health after code changes.

## Shipped

- `channels.create` is exposed through MCP.
- `POST /v1/workspaces/{workspace}/channels` is exposed through the local API.
- The shared service normalizes names, resolves invitees before creating, reuses compatible mirrored same-name channels, and persists channel/member state.
- `slack-mirror-channel-management` is bundled and installed for Codex, OpenClaw, and Gemini skill runtimes.
- No real Slack channel was created during validation.
