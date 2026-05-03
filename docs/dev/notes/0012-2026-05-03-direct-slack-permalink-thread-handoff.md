# Direct Slack Permalink And Thread Retrieval Handoff

Date: 2026-05-03

Source repo/session: `soylei-website`

## Trigger

The operator provided a direct Slack permalink to a SoyLei `#website` thread:

`https://soyleiinnovations.slack.com/archives/C06L8DVBWQP/p1777774228756839?thread_ts=1777682271.668819&cid=C06L8DVBWQP`

The expected workflow was straightforward: resolve that permalink, retrieve the
thread text and any images/files, and summarize Michael's issues. Instead, the
agent took several trial-and-error steps before using the correct local CLI
surface.

## What Was Difficult

- The available MCP tools did not expose a direct `permalink -> thread context`
  operation.
- `slack_mirror.conversations_list` could not resolve the SoyLei `#website`
  channel by name; it only found older `website` channels in other workspaces.
- `imcli.messages` with `tenant=soylei`, `service=slack`, and
  `thread=1777682271.668819` returned no messages.
- `imcli.search_messages` against the channel/thread was brittle for timestamp
  queries and hit an FTS syntax error when the query included a dotted Slack
  timestamp.
- A browser fallback opened the Slack permalink but hit the Slack sign-in page,
  which is a poor default for an already mirrored thread.
- The useful route was eventually discovered by inspecting CLI help and running:

```bash
slack-mirror-user messages list \
  --workspace soylei \
  --channels C06L8DVBWQP \
  --after 1777682200 \
  --before 1777774300 \
  --limit 200 \
  --json
```

Then filtering locally for:

```jq
.[] | select(.thread_ts=="1777682271.668819" or .ts=="1777682271.668819")
```

That returned the target thread and Michael's review note.

## Why This Should Have Been Easy

The permalink contains all required routing information:

- workspace domain: `soyleiinnovations`
- channel id: `C06L8DVBWQP`
- message ts: `1777774228.756839`, encoded in `/p1777774228756839`
- thread root ts: `1777682271.668819`

An agent should not need to search by keywords or open the Slack web app when a
direct pointer includes the workspace, channel, message timestamp, and thread
timestamp.

## Recommended Function Surface

Add a first-class MCP/API/CLI workflow for direct permalink lookup:

```text
slack permalink resolve <url> --json
```

Returned fields should include:

- workspace slug/domain/team id
- channel id/name/type
- message ts
- thread root ts
- whether the message is mirrored
- whether the thread root is mirrored
- suggested next command/action target

Then expose:

```text
slack thread get --workspace <workspace> --channel <channel_id> --thread-ts <ts> --json
```

The thread getter should return:

- root message
- replies in chronological order
- user display labels
- Slack text rendered safely for agent review
- attached files/images with local file path, public/private source metadata,
  OCR/derived text status, and thumbnails if available
- a compact summary-friendly text block

The MCP equivalent should ideally be one call:

```text
thread.from_permalink(url, include_text=true, include_files=true)
```

## Recommended Skill Updates

Update `slack-mirror-search` and/or add a dedicated permalink skill:

- If the user provides a Slack URL with `/archives/<channel>/p<ts>`, parse it
  first.
- Do not start with semantic/hybrid search.
- Do not use browser Slack unless mirror lookup fails and the operator really
  needs live Slack state.
- Convert `/p1777774228756839` to `1777774228.756839`.
- Prefer `thread_ts` from the URL query when present.
- Use exact channel id and a bounded time window only as a fallback until a
  direct thread API exists.
- Escape dotted Slack timestamps before sending them to FTS-backed search.
- When a thread lookup returns no rows, run a freshness/status diagnostic for
  that workspace/channel before trying unrelated workspace-wide searches.

## Acceptance Criteria

- Given the exact permalink above, an agent can retrieve Michael's thread note
  in one MCP/CLI workflow without browser auth.
- The workflow returns enough context to distinguish the root message from the
  selected reply.
- If images/files are attached to any thread message, the workflow returns
  attachment metadata and local review paths or a clear "not mirrored" status.
- The agent-facing skill examples include this SoyLei permalink as a regression
  example.

## Validation From The Incident

The CLI fallback did retrieve the thread. The relevant Michael Forrester message
was:

- bottom content appears to cut off
- hide the Applications page/nav entry
- remove the legacy "Formerly SIP-1132" APEX text

The difficulty was not data absence; it was missing direct permalink/thread
operator ergonomics.
