# LitScout-Informed Attachment Query Operators

State: CLOSED
Roadmap: P10
Opened: 2026-04-21
Closed: 2026-04-21

## Current State

- Slack Mirror message search has a small token parser that handles Slack-owned message operators such as `from:`, `in:`, `before:`, `after:`, `since:`, `until:`, `on:`, `has:link`, and `is:`.
- Derived-text search currently treats any token containing `:` as non-text, but it does not convert recognized file or attachment prefixes into structured filters.
- Corpus routing currently treats all `has:` operators as message-lane operators, which is correct for `has:link` but wrong for `has:attachment`.
- `../litscout` has a stronger parser/normalizer pattern:
  - tokenize phrases and fielded phrases predictably
  - normalize boolean-ish syntax with best-effort cleanup
  - extract recognized prefixes into `prefix_filters`
  - prune those prefixes from service-ready free text so they do not leak into backend query strings
  - keep provider/service-specific mapping outside the generic tokenizer

## Scope

- Add a Slack-owned query syntax helper for the immediate corpus-search needs rather than copying LitScout's domain-heavy parser.
- Add structured derived-text filters for:
  - `has:attachment`
  - `filename:`
  - `mime:`
  - `extension:` / `ext:`
  - `attachment-type:` as a portable alias for broad file media families where practical
- Make corpus lane selection distinguish message-lane operators from derived-text/file-lane operators.
- Ensure recognized file operators are stripped from derived-text lexical and semantic query terms while still applying structured SQL filters.
- Add unit coverage for lane routing and attachment/file filters.

## Non-Goals

- Do not extract a shared cross-repo parser yet; LitScout is an input pattern, not the source of truth for this repo.
- Do not add full boolean AST parsing for Slack Mirror in this slice.
- Do not change ranking defaults, embedding defaults, or retrieval-profile policy.
- Do not infer message-to-file joins beyond the schema that exists today; attachment operators in this slice target derived file/canvas text rows, not unindexed Slack message attachment metadata.

## Acceptance Criteria

- `has:attachment` returns derived file text rows instead of suppressing derived-text search as a message-lane operator.
- `filename:`, `mime:`, and `extension:` filter derived-text results by file/canvas metadata while preserving normal free-text matching.
- Recognized attachment/file operators do not become text terms for FTS or embedding query text.
- Existing message-lane filtering behavior from `0087` remains intact.
- Tests cover lexical, semantic query-term stripping, and corpus mixed-lane routing.
- Operator docs and generated CLI/man docs are updated.

## Definition Of Done

- Targeted unit tests pass.
- The broader service/API/MCP search suite passes if touched surfaces warrant it.
- Generated docs are current if CLI help text changes.
- Planning audit passes.
- Managed release check passes or records only expected non-blocking warnings.
- Evidence is recorded in `RUNBOOK.md`.

## Outcome

- Added a small Slack-owned `slack_mirror.search.query_syntax` helper inspired by LitScout's prefix-filter pattern.
- Derived-text lexical and semantic search now extracts and applies `has:attachment`, `filename:`, `mime:`, `extension:`/`ext:`, and `attachment-type:` filters.
- Recognized attachment/file operators are pruned from derived-text FTS and semantic embedding query text.
- Corpus search now distinguishes message-lane and attachment/file-lane operators:
  - message-lane filters suppress unfiltered derived-text hits
  - attachment/file-lane filters suppress unfiltered message hits
  - mixed message-lane plus file-lane filters return no inferred cross-lane join results until a future schema slice adds explicit message-to-file linkage
- CLI help, README, config docs, API/MCP contract docs, generated CLI docs, and man docs are updated.
