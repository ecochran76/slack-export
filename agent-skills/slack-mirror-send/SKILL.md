---
name: slack-mirror-send
description: Send Slack messages or thread replies through Slack Mirror's MCP/API outbound tools, including DM-style user targets, tenant/workspace routing, bot-vs-user auth mode, idempotency keys, and safe real-write preflight. Use for requests like "Send Michael a note about this on the SoyLei tenant from my user account", "DM Eric from the app", or "reply in this Slack thread".
---

# Slack Mirror Send

Use this skill for real outbound Slack writes through Slack Mirror.

## Default route

Prefer MCP tools when available:

1. `health`
2. `runtime.status`
3. `workspace.status` with the target workspace
4. `messages.send` or `threads.reply`

Fallback API routes:

- `POST /v1/workspaces/{workspace}/messages`
- `POST /v1/workspaces/{workspace}/threads/{thread_ref}/replies`

## Required fields

- `workspace`: Slack Mirror tenant/workspace, for example `soylei`, `default`, or `pcg`.
- `channel_ref`: channel id/name or DM-style user target.
- `text`: message body.
- `options.idempotency_key`: required by this skill for agent sends.

For thread replies also provide:

- `thread_ref`: Slack thread timestamp/reference.

## Tenant and auth routing

- If the user says "SoyLei tenant", use `workspace: "soylei"`.
- If the user says "PCG" or "polymer", use `workspace: "pcg"` unless live workspace discovery says otherwise.
- If the user says "default", "policy", or gives no tenant and context clearly points to the default install, use `workspace: "default"`.
- If tenant is not clear, call `workspaces.list`; ask only if still ambiguous.
- If the user says "from my user account", include `options: {"auth_mode": "user", ...}`.
- If the user says "from the app", "bot", or does not specify sender mode, use the default bot/app mode.

## Recipient routing

`channel_ref` accepts:

- Slack channel id: `C...`, `G...`, or `D...`
- Channel name: `general`
- User id or mention: `U...` or `<@U...>`
- DM-style user reference: `@Michael`, `@Eric`, `@username`

For a person-name request like "Send Michael...", use `channel_ref: "@Michael"`.
Slack Mirror resolves this against mirrored Slack users and opens a DM. If the
tool returns an ambiguous-user error, use `conversations.list` or ask the user
for the intended Slack user.

## Idempotency

Always include an idempotency key on agent writes. Use a stable key that would
not collide with unrelated sends, for example:

`agent-<workspace>-<recipient-slug>-<YYYYMMDD>-<short-purpose-slug>`

If retrying after a timeout or transport failure, reuse the same key. If sending
a new message with changed text, use a new key.

## Write policy

- Outbound tools are real Slack writes.
- If workspace, recipient, sender mode, and message content are clear, perform
  the send; do not add a redundant confirmation round trip.
- Ask a concise clarification if the recipient, tenant, or message body is
  ambiguous.
- Do not send secrets, tokens, private credentials, or raw logs.
- After sending, report `status`, `channel_id`, `ts` when present, and whether
  `idempotent_replay` was true.

## Examples

User: "Send Michael a note about this on the SoyLei tenant from my user account"

MCP call:

```json
{
  "workspace": "soylei",
  "channel_ref": "@Michael",
  "text": "<short note derived from current context>",
  "options": {
    "auth_mode": "user",
    "idempotency_key": "agent-soylei-michael-20260501-context-note"
  }
}
```

User: "Reply in that thread from the app"

MCP call:

```json
{
  "workspace": "soylei",
  "channel_ref": "C123456",
  "thread_ref": "1712870400.000100",
  "text": "<reply>",
  "options": {
    "idempotency_key": "agent-soylei-c123456-20260501-thread-reply"
  }
}
```
