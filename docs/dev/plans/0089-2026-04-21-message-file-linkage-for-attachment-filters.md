# Message-File Linkage For Attachment Filters

State: CLOSED
Roadmap: P10
Opened: 2026-04-21
Closed: 2026-04-21

## Current State

- `0088` added attachment/file query operators for derived-text rows:
  - `has:attachment`
  - `filename:`
  - `mime:`
  - `extension:` / `ext:`
  - `attachment-type:`
- Corpus routing now avoids leaking unfiltered rows across message and derived-text lanes.
- Mixed message-lane plus attachment-lane filters currently return no inferred join results because the DB does not persist a first-class message-to-file relationship.
- Slack message payloads already carry `files[]`, and `upsert_message` already upserts those file rows, so the missing piece is a durable link table and search clauses over it.

## Scope

- Add a `message_files` table that links messages to Slack file ids.
- Populate that table from `message.files[]` during `upsert_message`.
- Add message-search support for:
  - `has:attachment`
  - `filename:`
  - `mime:`
  - `extension:` / `ext:`
  - `attachment-type:`
- Update corpus lane selection so mixed message/file filters can return message rows when message-file linkage can satisfy the attachment constraints.
- Keep derived-text file filtering from `0088` intact.

## Non-Goals

- Do not infer historical message-file links from `files.raw_json`; the only backfill source for this slice is stored Slack `messages.raw_json`.
- Do not change export bundle behavior.
- Do not require derived-text extraction to make message-level attachment filters work.
- Do not introduce a shared parser package yet.

## Acceptance Criteria

- New migrations create `message_files` with deterministic constraints and indexes, then backfill existing links from `messages.raw_json`.
- `upsert_message` refreshes message-file links idempotently.
- `search_messages` can answer message-scoped `has:attachment` and file metadata filters.
- `search_corpus` can return message rows for mixed message-lane plus attachment/file filters such as `on:YYYY-MM-DD has:attachment extension:pdf`.
- Unit tests cover link persistence, metadata filtering, and corpus mixed-lane behavior.
- Docs and generated CLI/man pages are updated if operator descriptions change.

## Definition Of Done

- Targeted DB and search tests pass.
- Broader search/service tests pass if shared search behavior changes.
- Generated docs are current if CLI help changes.
- Planning audit passes.
- Evidence is recorded in `RUNBOOK.md`.

## Outcome

- Added migration `0012_message_files.sql` with a durable message/file edge table.
- Added migration `0013_message_files_backfill.sql` to populate existing links from stored Slack message payloads.
- `upsert_message` now refreshes linked file ids from Slack `message.files[]` while preserving existing file upsert behavior.
- Message search now applies `has:attachment`, `filename:`, `mime:`, `extension:`/`ext:`, and `attachment-type:` through linked file metadata.
- Corpus search can return message rows for mixed message-lane plus attachment/file filters when message-file linkage satisfies both sides.
- Derived-text attachment filtering from `0088` remains intact.
