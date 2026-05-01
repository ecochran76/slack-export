---
name: slack-mirror-search
description: Run and interpret Slack Mirror keyword/semantic/hybrid search with workspace/channel/date/person scoping, conversation discovery, context expansion, and relevance cross-checks. Use for requests like "What did Baker say about amazon today?", "find X in workspace Y", "semantic search for terms", "search seems noisy", and "confirm indexing freshness via query behavior".
---

# Slack Mirror Search

## Default route

Prefer MCP tools when available:

1. `health`
2. `runtime.status`
3. `workspace.status` for the target workspace
4. `search.corpus` for broad corpus search
5. `search.conversation` when the user names a channel/person/conversation
6. `search.context_pack` when hits need surrounding messages

Fallback CLI:

- `slack-mirror-user search corpus --workspace <ws> --query "..." --mode <mode> --limit <n> --json`
- `slack-mirror-user search context-pack --targets-json '<targets>' --before 2 --after 2 --json`

## Query modes

- Semantic: concept match; may be noisy on niche terms.
- Keyword: literal precision; best for rare names/tickers/brands.
- Hybrid: combine both; useful default for broad queries.

## Common user asks

For "What did Baker say about amazon today?":

1. Resolve workspace from user context; if unknown, use `all_workspaces: true`
   or call `workspaces.list`.
2. Build a lexical-first query with speaker and date constraints:
   `from:Baker amazon on:<YYYY-MM-DD>`.
3. Call `search.corpus` with `mode: "lexical"`, `limit: 10`, and the workspace
   or `all_workspaces: true`.
4. If no hits, try `participant:Baker amazon on:<YYYY-MM-DD>`, then hybrid.
5. Use `search.context_pack` on the best `action_target` values when a hit
   needs surrounding context before answering.
6. Answer with the substance, channel, timestamp, and confidence; say when no
   matching mirrored messages were found.

For named conversations or DMs:

- Use `conversations.list` with `member_query`, `name_query`, or
  `channel_type`, then `search.conversation`.
- Do not guess private channel ids from display text.

## Query operators

Useful message-lane operators:

- `from:<name>`
- `participant:<name>`
- `user:<name-or-id>`
- `in:<channel_id>`
- `channel:<name>`
- `on:YYYY-MM-DD`
- `after:YYYY-MM-DD`
- `before:YYYY-MM-DD`
- `has:attachment`
- `is:thread`, `is:reply`, `is:edited`

Attachment and OCR operators:

- `filename:<term>`
- `mime:<type>`
- `extension:<ext>` or `ext:<ext>`
- `attachment-type:<kind>`

## Core CLI commands

- Semantic:
  - `slack-mirror-user search corpus --workspace <ws> --query "..." --mode semantic --retrieval-profile baseline --limit <n> --json`
- Keyword:
  - `slack-mirror-user search corpus --workspace <ws> --query "..." --mode lexical --limit <n> --json`
- Hybrid:
  - `slack-mirror-user search corpus --workspace <ws> --query "..." --mode hybrid --retrieval-profile baseline --limit <n> --json`

## Relevance workflow

1. Start lexical for exact people, companies, dates, tickers, URLs, and quoted
   terms.
2. Use hybrid for broad conceptual questions or after lexical misses.
3. Use semantic only when the user wants conceptual similarity.
4. Expand context around selected `action_target` rows before summarizing
   anything ambiguous.
5. Return strongest hits with channel, timestamp, excerpt, and why relevant.
6. Flag confidence and caveats.

## Reporting format

- Separate by query term when user gives multiple terms.
- For each hit include: channel, timestamp, excerpt, why relevant.
- State when lexical was used to rescue noisy semantic output.
- For "what did X say" answers, summarize the answer first, then list the
  backing Slack hits.
