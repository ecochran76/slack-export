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

This is intentionally separate from message search while the broader hybrid retrieval contract is still under `P03`.

Chunk semantics:

- long derived-text rows are split into overlapping retrieval chunks
- search still resolves and returns the owning `derived_text` row
- result payloads may include:
  - `matched_text`
  - `chunk_index`
  - `start_offset`
  - `end_offset`
- callers should treat those as best-match snippet metadata, not as a separate document identity

## Remaining Work

- hybrid retrieval over messages plus derived-text rows
- broader benchmark depth beyond smoke fixtures
- richer backlog and outcome reporting for extraction coverage
- OCR coverage reporting and fallback/provider routing beyond local host tools
