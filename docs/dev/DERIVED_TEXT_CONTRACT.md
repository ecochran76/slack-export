# Derived Text Contract

This document defines the first shared-core contract for searchable non-message text in Slack mirror.

## Purpose

Slack mirror already stores:

- canonical message text in `messages`
- file metadata in `files`
- canvas metadata in `canvases`

This slice adds the first explicit derived-text layer so search can grow beyond message bodies without inventing ad hoc extractor-owned tables.

## Shared Tables

Derived text now lives in:

- `derived_text`
- `derived_text_fts`
- `derived_text_jobs`

These are shared-core tables. They are not extractor-private state.

## Current Source Kinds

- `file`
- `canvas`

## Current Derivation Kinds

- `attachment_text`
- `ocr_text`

Semantics:

- `attachment_text` means machine-readable text obtained without OCR
- `ocr_text` is reserved for optical character recognition from image-like content

## Current Extractors

Implemented:

- `canvas_html`
  - strips and normalizes text from downloaded Slack canvas HTML
- `utf8_text`
  - extracts text from safe UTF-8 text-like files such as `.txt`, `.md`, `.csv`, `.json`, and `.html`
- `pdftotext`
  - extracts machine-readable PDF text when the `pdftotext` CLI is available

Reserved but not yet implemented:

- OCR extractors for image blobs and scanned/image-heavy PDFs

## Ownership Rules

1. Derived text is shared searchable state, not cache-only extraction output.
2. Message search and derived-text search are separate surfaces.
3. `attachment_text` and `ocr_text` must remain distinguishable in storage and query results.
4. New extractors must write through the shared `derived_text` contract instead of adding extractor-specific tables.
5. Search, CLI, API, and MCP work should resolve back to shared-core rows rather than extractor-private artifacts.

## Queue Semantics

`derived_text_jobs` is the backlog table for extraction work.

Current behavior:

- file and canvas ingestion enqueue `attachment_text` jobs when local content is present
- `slack-mirror mirror process-derived-text-jobs` processes queued extraction work for one derivation kind
- unsupported or not-yet-implemented derivation kinds are skipped explicitly rather than silently ignored

## Search Surface

The current CLI surface is:

```bash
slack-mirror search derived-text --workspace <name> --query <text>
```

Optional filters:

- `--kind attachment_text|ocr_text`
- `--source-kind file|canvas`

This is intentionally separate from message search while the broader hybrid retrieval contract is still under `P03`.

## Remaining Work

- OCR extraction for image blobs and scanned/image-heavy PDFs
- chunking for long attachment and canvas text
- hybrid retrieval over messages plus derived-text rows
- API and MCP exposure for derived-text search
- richer backlog and outcome reporting for extraction coverage
