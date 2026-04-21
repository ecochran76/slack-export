# Portable Query Date Operators

State: CLOSED
Roadmap: P10
Opened: 2026-04-21
Closed: 2026-04-21

## Current State

- Slack Mirror message search supports `from:`, `in:`, `source:`/`channel:`, `before:`, `after:`, `has:link`, and basic `is:` filters.
- The cross-corpus convergence plan already calls out portable temporal operators such as `before:`, `after:`, `since:`, `until:`, and `on:`.
- The current `before:` and `after:` implementation compares raw values as Slack timestamp floats, so ISO dates such as `2026-04-21` do not behave as operator users expect.
- Query-variant benchmark evidence showed broad automatic normalization is not safe to promote, making explicit grammar a safer next relevance surface.

## Scope

- Add parser-backed date handling for ISO dates and ISO datetimes in message search.
- Add portable temporal aliases:
  - `since:` as an alias for lower-bound search.
  - `until:` as an alias for upper-bound search.
  - `on:` as a UTC date/day range.
- Add a portable actor alias where safe:
  - `participant:` and `user:` should behave like Slack sender `from:` for message search.
- Preserve existing unqualified query behavior and numeric Slack timestamp filters.

## Non-Goals

- Do not change semantic embedding generation or retrieval-profile defaults.
- Do not introduce automatic query rewriting.
- Do not extract a shared cross-repo query parser yet; that remains gated on compatible behavior across at least two repos.
- Do not add file/attachment operators in this slice.

## Acceptance Criteria

- Message lexical, semantic, hybrid, and corpus searches can apply `since:`, `until:`, and `on:` filters through the existing query parser.
- `before:` and `after:` continue to accept numeric Slack timestamps.
- ISO date filters are converted to Unix timestamp ranges deterministically.
- Unit tests cover numeric timestamp compatibility, ISO date range behavior, `on:`, and actor aliases.
- README/config/benchmark or CLI docs are updated where operator examples live.
- Managed install and live smoke evidence prove the new operators work without changing ranking defaults.

## Definition Of Done

- Targeted unit tests pass.
- Generated docs are current if the CLI surface changes.
- Planning audit passes.
- Managed release check passes or records only expected non-blocking warnings.
- Evidence is recorded in `RUNBOOK.md`.

## Outcome

- Message search now accepts ISO date/datetime temporal filters in addition to numeric Slack timestamps.
- `since:` and `until:` are supported as portable aliases for lower and upper bounds.
- `on:YYYY-MM-DD` expands to a UTC day range.
- `participant:` and `user:` are supported as Slack sender aliases.
- Corpus search now suppresses derived-text hits when message-lane operators are present, avoiding unfiltered attachment/OCR results for timestamp, sender, and channel constrained queries.
- Shared parser extraction remains deferred until compatible behavior is proven in a second communications repo.
