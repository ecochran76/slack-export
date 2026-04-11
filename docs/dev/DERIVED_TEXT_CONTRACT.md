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

Chunk-owned retrieval state now also lives in:

- `derived_text_chunks`
- `derived_text_chunks_fts`

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
- `ooxml_docx`
  - extracts text from `.docx` attachments through OOXML XML parts
- `ooxml_pptx`
  - extracts text from `.pptx` slide XML parts
- `ooxml_xlsx`
  - extracts text from `.xlsx` shared strings and worksheet XML parts
- `pdftotext`
  - extracts machine-readable PDF text when the `pdftotext` CLI is available
- `tesseract_image`
  - extracts OCR text from image-like files when `tesseract` is available
- `tesseract_pdf`
  - extracts OCR text from scanned/image-heavy PDFs by rendering pages with `pdftoppm` and OCRing them with `tesseract`

Current OCR boundary:

- `ocr_text` is currently supported for files, not canvases
- PDFs with a machine-readable text layer stay `attachment_text` only; their `ocr_text` jobs are skipped as `pdf_has_text_layer`
- OCR depends on local host tools rather than a remote provider in this slice

## Provider Boundary

- derived-text job execution now runs through a shared extraction-provider seam
- `LocalCliDerivedTextProvider` is the current default implementation
- `CommandDerivedTextProvider` is now supported as an optional configured provider
- `HttpDerivedTextProvider` is now supported as an optional configured provider
- remote providers are wrapped with local fallback by default unless `fallback_to_local: false` is set
- provider identity is recorded in derived-text metadata as `provider`
- new provider-backed extraction or OCR paths must preserve the existing `attachment_text` and `ocr_text` contract instead of inventing new derivation kinds

Command-provider contract:

- selection happens through `search.derived_text.provider`
- `type: command` requires a configured `command`
- Slack mirror sends one JSON object on stdin with:
  - `action`
    - `attachment_text`
    - `ocr_text`
  - `workspace_id`
  - `source_kind`
  - `source_id`
  - `local_path`
  - `media_type`
  - optional `title`
  - optional `name`
- the provider must write one JSON object to stdout:
  - success:
    - `ok: true`
    - `text`
    - optional `extractor`
    - optional `details`
  - failure/skip:
    - `ok: false`
    - `error`
- provider `details` are merged into derived-text metadata and must stay compatible with shared-core ownership
- when local fallback is used, metadata records the actual provider as `local_host_tools` plus `fallback_from` and `fallback_error`

HTTP-provider contract:

- selection happens through `search.derived_text.provider`
- `type: http` requires a configured absolute `url`
- optional `headers` are sent with each request
- optional `bearer_token_env` injects `Authorization: Bearer ...` from the named environment variable
- optional `timeout_s` controls request timeout
- optional `fallback_to_local` controls whether failed remote extraction falls back to the built-in local provider; default is enabled
- Slack mirror sends the same JSON request body used by the command provider
- the HTTP endpoint must return the same JSON response contract used by the command provider

## Ownership Rules

1. Derived text is shared searchable state, not cache-only extraction output.
2. Message search and derived-text search are separate surfaces.
3. `attachment_text` and `ocr_text` must remain distinguishable in storage and query results.
4. New extractors must write through the shared `derived_text` contract instead of adding extractor-specific tables.
5. Search, CLI, API, and MCP work should resolve back to shared-core rows rather than extractor-private artifacts.
6. Chunk rows are retrieval-serving children of `derived_text`, not a second canonical document store.

## Queue Semantics

`derived_text_jobs` is the backlog table for extraction work.

Current behavior:

- file and canvas ingestion enqueue `attachment_text` jobs when local content is present
- OCR-eligible files also enqueue `ocr_text` jobs when local content is present
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

This is intentionally separate from message search even though the broader corpus-retrieval contract is now shipped through `search corpus`.

Chunk semantics:

- long derived-text rows are split into overlapping retrieval chunks
- search still resolves and returns the owning `derived_text` row
- result payloads may include:
  - `matched_text`
  - `chunk_index`
  - `start_offset`
  - `end_offset`
- callers should treat those as best-match snippet metadata, not as a separate document identity

## Remaining Follow-On Work

- richer backlog and outcome reporting for extraction coverage
- OCR coverage reporting and fallback/provider routing beyond local host tools
- broader document-format coverage beyond the current UTF-8, PDF, and OOXML baseline
- future semantic-ranking improvements beyond the current local hybrid baseline
