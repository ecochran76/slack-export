---
name: slack-mirror-channel-management
description: Create or reuse Slack channels through Slack Mirror MCP/API, including tenant routing, public/private selection, invitee resolution, and bot-vs-user auth mode. Use for requests like "create a private channel on SoyLei called project-alpha and invite Baker and Michael" or "make a Slack channel for this from the app".
---

# Slack Mirror Channel Management

Use this skill for real Slack channel-management writes through Slack Mirror.

## Default route

Prefer MCP tools when available:

1. `health`
2. `runtime.status`
3. `workspace.status` with the target workspace
4. `channels.create`

Fallback API route:

- `POST /v1/workspaces/{workspace}/channels`

## Required fields

- `workspace`: Slack Mirror tenant/workspace, for example `soylei`, `default`, or `pcg`.
- `name`: requested channel name. Slack Mirror normalizes this to a Slack-compatible lowercase channel name.
- `is_private`: `true` for private channels, `false` for public channels.
- `invitees`: optional list of user references such as `Baker`, `@Michael`, `<@U123>`, or `U123`.

## Tenant and auth routing

- If the user says "SoyLei tenant", use `workspace: "soylei"`.
- If the user says "PCG" or "polymer", use `workspace: "pcg"` unless live workspace discovery says otherwise.
- If the user says "default", "policy", or gives no tenant and context clearly points to the default install, use `workspace: "default"`.
- If tenant is not clear, call `workspaces.list`; ask only if still ambiguous.
- If the user says "from my user account", include `options: {"auth_mode": "user"}`.
- If the user says "from the app", "bot", or does not specify sender mode, use the default bot/app mode.

## Write policy

- Channel creation and invitations are real Slack mutations.
- If workspace, channel name, privacy, and invitees are clear, perform the action; do not add a redundant confirmation round trip.
- Ask a concise clarification if the tenant, channel name, privacy, or invitee list is ambiguous.
- Slack Mirror resolves invitee names before creating a new channel. If a user is missing or ambiguous, stop and report the specific unresolved reference.
- Slack Mirror reuses an already mirrored same-name channel only when the requested public/private setting matches.

## Example

User: "Please create a channel on the SoyLei tenant called Project Alpha. Make it private and invite Baker and Michael."

MCP call:

```json
{
  "workspace": "soylei",
  "name": "Project Alpha",
  "is_private": true,
  "invitees": ["Baker", "Michael"],
  "options": {}
}
```

Report back:

- normalized channel name
- channel id
- whether it was newly created or reused
- invited user ids or unresolved invitees if the tool failed
