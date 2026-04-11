# Extraction Provider Expansion

State: CLOSED
Roadmap: P03
Opened: 2026-04-11
Follows: `docs/dev/plans/0006-2026-04-11-search-evaluation-modernization.md`

## Scope

Define the next bounded search follow-up after the SQLite-first baseline so Slack mirror can improve non-message corpus coverage without breaking the shared search core.

This plan is specifically about:

- provider-routed OCR and extraction beyond the current host-local toolchain
- richer extraction outcome reporting and operator visibility
- careful expansion of attachment/document coverage where it fits the existing `derived_text` ownership model

This plan is not a generic reopening of broad search modernization.

## Current State

- the current shipped extractor set is host-local and SQLite-first:
  - `canvas_html`
  - `utf8_text`
  - `ooxml_docx`
  - `ooxml_pptx`
  - `ooxml_xlsx`
  - `odf_odt`
  - `odf_odp`
  - `odf_ods`
  - `pdftotext`
  - `tesseract_image`
  - `tesseract_pdf`
- extracted text is already owned through shared-core `derived_text`, `derived_text_jobs`, and `derived_text_chunks`
- corpus retrieval, readiness, and health are already shipped through CLI, API, and MCP
- an initial extraction-provider boundary is now landed, with `LocalCliDerivedTextProvider` as the default implementation
- provider identity is now recorded in derived-text metadata so later coverage reporting can distinguish host-local versus future provider-routed extraction paths
- the main weakness at plan open was not corpus shape; it was extraction depth and operational visibility
- `../ragmail` demonstrated the value of provider/router abstraction, richer OCR fallback, and stronger extraction diagnostics
- `../imcli` demonstrated the importance of keeping `attachment_text` and `ocr_text` explicit while making coverage operationally visible

## Goals

1. Add a bounded provider boundary for extraction and OCR without changing the shared `derived_text` contract.
2. Preserve the current host-local toolchain as the default baseline and fallback path.
3. Make extraction outcomes more machine-readable and operator-visible.
4. Expand format coverage only where the result still fits shared-core ownership and search semantics.

## Parallel Tracks

### Track A | Provider Boundary

- define a clean extractor/OCR provider interface in shared code
- keep local CLI-tool extraction as one provider implementation
- allow optional remote/provider-backed OCR or extraction without making it a hard dependency

Current status:

- the shared provider seam is landed
- the local host-tools implementation remains the default
- command-backed and HTTP-backed providers are landed behind config selection, with local fallback enabled by default
- richer remote/provider-backed implementations remain explicitly deferred to a future narrow follow-up instead of keeping this plan open indefinitely

### Track B | Outcome Reporting

- improve machine-readable reporting for extraction success, skip, unsupported, and failure outcomes
- make coverage and backlog status visible enough for operators and eval tooling
- keep reporting aligned with the existing search-health and readiness model where appropriate

Current status:

- `search.readiness` now reports per-derivation provider coverage, job status buckets, and issue reasons
- the same richer readiness payload now flows through existing CLI, API, and MCP surfaces
- extraction-health thresholding is landed through `search.health`; deeper coverage policy is deferred to any future narrow follow-up

### Track C | Format Expansion

Current status:

- `.docx` extraction is now story-aware across body, headers, footers, footnotes, and endnotes, using visible-text handling instead of a document-body-only XML flattening path
- `.pptx` and `.xlsx` extraction now use visible-text-aware slide parsing and shared-string-aware worksheet parsing instead of a generic XML flattening path


- review the next highest-value attachment formats after the current UTF-8, PDF, and OOXML baseline
- only add formats that can map cleanly to `attachment_text` or `ocr_text`
- avoid extractor-specific side tables or format-specific search semantics

Current note:

- `docx-skill` appears to contain reusable OOXML story/text primitives that could improve both `.docx` extraction quality and future chat-export DOCX rendering, but that reuse is intentionally deferred until it can be scoped as a bounded export/extraction slice rather than folded into this plan ad hoc

## Closure Basis

- a shared provider boundary now exists for extraction and OCR paths
- the current host-local extractor path remains supported and default
- extraction outcome reporting is explicit and machine-readable through readiness and search-health surfaces
- post-baseline provider and format-expansion slices are shipped through command, HTTP, local-fallback, OOXML, and OpenDocument coverage without changing the shared `derived_text` contract

## Deferred Follow-Up

- provider-specialized OCR or extraction beyond the current generic command/HTTP seam
- deeper extraction coverage policy if future operators need stronger guarantees than the current readiness and health signals
- reuse of `docx-skill` OOXML primitives for future export-quality DOCX rendering or further extraction fidelity improvements

## Non-Goals

- replacing the SQLite-first search baseline
- making a remote provider mandatory for normal installs
- introducing a second canonical storage model for extracted text
- reopening generic ranking or backend work already bounded elsewhere

## Acceptance Criteria

- a shared provider boundary exists for extraction and OCR paths
- the current host-local extractor path remains supported and default
- extraction outcome reporting is more explicit and machine-readable than today
- at least one post-baseline provider or format-expansion slice is documented and bounded against the shared `derived_text` contract

## Definition Of Done

This plan is done when Slack mirror has a documented and shipped post-baseline extraction follow-up with a real provider boundary, better extraction visibility, and bounded expansion rules that preserve the existing shared-core search model.
