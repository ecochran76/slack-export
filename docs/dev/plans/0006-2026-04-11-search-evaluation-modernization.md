# Search Evaluation Modernization

State: CLOSED
Roadmap: P03
Opened: 2026-04-11
Supersedes: `docs/dev/PHASE_E_SEMANTIC_SEARCH.md`, `docs/dev/PHASE_F_SEARCH_PLATFORM.md`, `docs/dev/SEARCH_EVAL.md`

## Scope

Define the next bounded search lane for Slack mirror so the repo can move from:

- workspace-scoped message search
- message-only embeddings
- Slack-specific retrieval assumptions

to a world-class search stack with:

- cross-tenant lexical search
- lexical-first semantic retrieval
- attachment- and canvas-derived text
- OCR for image-like and image-PDF content
- explicit evaluation and search-health discipline

## Current State

- `slack_mirror` already has SQLite-backed keyword, semantic, and hybrid search over mirrored messages
- lexical search uses `messages_fts`
- semantic search uses `message_embeddings`
- the current semantic baseline is SQLite-first and local-model-friendly, but it is still message-centric
- first-class derived-text storage is now landed through:
  - `derived_text`
  - `derived_text_fts`
  - `derived_text_jobs`
- the first document-native extraction slice is landed for:
  - downloaded canvas HTML
  - safe UTF-8 text-like files
  - OOXML office files (`.docx`, `.pptx`, `.xlsx`)
  - machine-readable PDFs when `pdftotext` is available
- OCR extraction is now landed for:
  - image-like files through `tesseract`
  - scanned/image-heavy PDFs through `pdftoppm` plus `tesseract`
  - PDFs with a real text layer are kept as `attachment_text` and explicitly skipped for `ocr_text`
- `search derived-text`, `search corpus`, and `mirror process-derived-text-jobs` now expose the current shared-core non-message and cross-corpus search surface
- the current corpus baseline is lexical-first hybrid retrieval over messages plus derived text
- explicit cross-workspace corpus search is now landed through the shared service, CLI, API, and MCP instead of remaining a future-only goal
- API and MCP now expose corpus search and machine-readable search readiness over the same shared service boundary
- a shared search-health gate now exists over readiness plus optional benchmark execution
- search-health now enforces stronger ranking-quality gates and exposes per-query benchmark diagnostics for misses and weak-ranking cases
- chunk-aware derived-text retrieval is now landed through `derived_text_chunks` plus `derived_text_chunks_fts`
- chunk-level matches now roll back up to shared-core derived-text results with snippet metadata instead of inventing a second document identity
- a deeper corpus benchmark pack now exists alongside the smoke fixture for long-document and OCR retrieval checks
- the current roadmap text is directionally right, but the active repo needs one explicit modernization plan instead of relying on older Phase E/F notes

## Cross-Repo Comparison

### Current `slack-export`

Strengths:

- already has a working lexical, semantic, and hybrid baseline in-repo
- already has query parsing, field filters, FTS maintenance, and a reusable adapter seam
- already has evaluation scaffolding and benchmark fixtures
- already has CLI, API, and MCP surfaces that can expose future search improvements cleanly

Gaps:

- search is still centered on `messages`, not a broader searchable corpus
- there is no first-class derived-text model for attachments, canvases, OCR, or image-PDF extraction
- semantic retrieval is message-embedding-only and uses a lightweight local path rather than an explicit provider boundary
- current search does not yet model cross-tenant retrieval as a first-class contract

### `../ragmail`

Adopt:

- explicit separation between canonical records and retrieval-serving assets
- chunk-oriented retrieval for messages and attachments
- staged attachment extraction with OCR and optional vision
- provider/router abstraction for OCR, vision, embeddings, and reranking
- stronger evaluation and retrieval diagnostics discipline

Do not copy directly:

- backend-first OpenSearch materialization as the initial requirement for Slack mirror
- heavy mail-specific corpus and archive machinery that is not needed for Slack-first modernization

### `../imcli`

Adopt:

- tenant-safe shared-core ownership of canonical search and derived text
- explicit separation between canonical message search and derived-text search
- disciplined distinction between document-native `attachment_text` and true `ocr_text`
- lexical-first hybrid retrieval with embeddings as derived state, not a second source of truth
- blob/derived-text/reporting seams that make attachment coverage operationally visible

Do not copy directly:

- service-merge assumptions that are specific to multi-messenger unification
- operator/runtime decisions that belong to `imcli` rather than Slack mirror

## Architectural Direction

Slack mirror should combine:

- the current repo's SQLite-first retrieval baseline
- `imcli`'s shared-core search and derived-text discipline
- `ragmail`'s extraction, OCR, chunking, and evaluation rigor

That means:

1. Keep one canonical Slack mirror DB as the system of record.
2. Add first-class derived-text tables for attachment-, canvas-, and OCR-derived text.
3. Keep lexical search as the durable baseline.
4. Use embeddings as derived state over both canonical message text and derived text.
5. Add chunking only where it materially improves attachment and long-document retrieval.
6. Keep API, MCP, and CLI search semantics aligned over the same shared search core.

## Parallel Tracks

### Track A | Searchable Corpus Expansion

- define first-class searchable units beyond `messages`
- add derived-text ownership for files, canvases, PDFs, and OCR
- define cross-tenant and cross-workspace query scope rules

### Track B | Extraction and OCR

- document-native extraction for machine-readable PDFs and safe text-like attachments
- OCR for image blobs and scanned/image-heavy PDFs
- extraction outcome tracking, backlog visibility, and failure semantics

### Track C | Retrieval and Ranking

- lexical-first hybrid retrieval over messages plus derived text
- provider boundary for real embeddings beyond the local hash scaffold
- chunking strategy for long attachment text and canvas text

### Track D | Evaluation and Diagnostics

- real benchmark sets beyond smoke fixtures
- quality comparison across lexical, semantic, and hybrid modes
- search-health and freshness checks for lexical, derived-text, OCR, and embedding readiness

Status on completion:

- Track A shipped on the shared `messages` plus `derived_text` corpus with explicit cross-workspace scope
- Track B shipped on the current host-local extractor set for canvases, UTF-8 files, OOXML files, machine-readable PDFs, and OCRable image/scanned-PDF content
- Track C shipped on lexical-first hybrid retrieval over messages plus derived text, with chunk-aware retrieval for long derived-text rows
- Track D shipped on shared readiness plus corpus smoke/depth benchmark gating, including per-query diagnostics and bounded ranking thresholds

## Critical Path

1. define the searchable corpus contract first
2. land derived-text and extraction ownership next
3. then expand hybrid retrieval to that broader corpus
4. make evaluation and readiness gates mandatory before tuning or backend expansion

## Non-Goals

- making OpenSearch or another remote backend a prerequisite for the first modernization slice
- adding vision-heavy multimodal reasoning to the baseline search contract
- rebuilding the current message-search path from scratch instead of evolving it
- importing sibling-repo storage models literally

## Acceptance Criteria

- the repo has one explicit active plan for search modernization
- search scope includes canonical messages plus first-class derived text
- attachment/PDF/OCR extraction semantics are documented and bounded
- hybrid retrieval is defined over the broader searchable corpus, not only message rows
- evaluation and readiness checks are part of the search contract

## Definition Of Done

This plan is done when Slack mirror has a documented and shipped search stack that supports cross-workspace lexical and semantic retrieval over message text plus derived attachment/OCR text, with explicit evaluation and operator readiness checks, and future search work no longer depends on the older Phase E/F notes as the active source of truth.

Closure note:

- This condition is now met on the current SQLite-first baseline.
- Explicitly deferred from closure:
  - remote/provider-routed OCR or extraction paths
  - broader office/document format coverage beyond the current shipped set
  - future ranking-model or backend changes beyond the current local hybrid baseline
  - deeper benchmark suites beyond the current smoke and depth packs
