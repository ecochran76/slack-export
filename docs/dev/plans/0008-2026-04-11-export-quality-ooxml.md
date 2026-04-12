# Export Quality OOXML

State: OPEN
Roadmap: P03
Opened: 2026-04-11
Follows: `docs/dev/plans/0007-2026-04-11-extraction-provider-expansion.md`

## Scope

Define a narrow post-search follow-up for export-quality OOXML and DOCX output so this repo can turn its stronger extraction knowledge into materially better chat export artifacts.

This plan is specifically about:

- improving export-quality OOXML handling for chat-export workflows
- identifying which `docx-skill` primitives are worth reusing without importing the whole skill blindly
- making DOCX-grade exports a first-class bounded capability instead of leaving exports at HTML and PDF only

This plan is not a generic reopening of search modernization or a commitment to full document-editing features.

## Current State

- the repo already ships export workflows for HTML, JSON, and PDF through:
  - `scripts/export_channel_day.py`
  - `scripts/export_channel_day_pdf.py`
  - `scripts/export_multi_day_pdf.py`
  - `scripts/export_semantic_daypack.py`
- the current export pipeline is centered on `export_channel_day.py`, which already defines the canonical per-day message bundle with:
  - thread-aware ordering
  - resolved user labels
  - attachment metadata and local file paths
- the PDF scripts are presentation layers over that JSON bundle; they are not independent export contracts
- `export_semantic_daypack.py` is an orchestrator that composes the channel/day export path rather than defining a separate artifact model
- the repo now has materially better OOXML extraction knowledge for search, especially for `.docx`, `.pptx`, and `.xlsx`
- `docx-skill` appears to contain reusable OOXML story/text primitives that could improve export fidelity, but that reuse has not yet been scoped for this repo
- the main gap is export quality, not search corpus shape

## Track A Decision

- the first DOCX-quality export target should be single channel/day export
- `scripts/export_channel_day.py` should remain the canonical content assembly path
- a future DOCX renderer should consume the same channel/day JSON bundle rather than re-querying SQLite independently
- multi-day bundles and semantic daypacks should compose from that same per-day DOCX artifact or its shared rendering primitives, instead of inventing a separate DOCX pipeline first
- this keeps one clear export ownership path and makes fixture-based QA tractable

## Goals

1. Audit the current export workflows against the repo's OOXML knowledge and identify the highest-value DOCX-quality target.
2. Reuse only the `docx-skill` primitives that fit deterministic export generation or validation cleanly.
3. Define one explicit export-quality contract for Slack chat output instead of leaving OOXML export as an accidental side idea.
4. Keep export-quality work bounded so it does not sprawl into generic office-document editing.

## Parallel Tracks

### Track A | Export Surface Audit

- review the existing HTML, JSON, and PDF export scripts
- identify where DOCX output belongs and where it does not
- decide whether the first target is channel/day export, multi-day bundles, semantic daypacks, or another bounded export artifact

Current status:

- audit completed
- the first target is channel/day export
- multi-day and semantic daypack output should build on the channel/day export artifact instead of introducing a second canonical DOCX path

### Track B | OOXML Primitive Reuse

- identify the minimal `docx-skill` story/text/structure primitives that are useful here
- reuse only what helps deterministic export rendering or export QA
- avoid importing mutation, review, or authoring features that do not serve Slack export output

Current status:

- the first implementation slice is intentionally self-contained and deterministic: a channel/day JSON -> DOCX renderer
- reuse of deeper `docx-skill` primitives is still deferred until the bounded renderer baseline is shipped and assessed

### Track C | Export Contract And QA

- define what a good DOCX-grade export means for this repo
- add bounded fixture-based validation for export output quality
- prefer render or structure checks that catch obvious formatting regressions

Current status:

- the first bounded renderer target is channel/day DOCX output over the canonical JSON artifact
- the first QA pass is package-structure and content-contract validation rather than visual polish
- the current implementation pass now includes explicit paragraph styles and richer attachment/source presentation within the same bounded renderer
- DOCX export validation now performs deeper OOXML package checks for:
  - XML and relationship-part parseability
  - content-type overrides that point to real parts
  - internal relationship targets that resolve to real parts
- the default DOCX rendering baseline is now visually reviewed through the local `docx-skill` render path and currently targets:
  - 1in page margins
  - sans-serif 10pt body text
  - compact header metadata
  - quieter human-readable attachment type labels
- the renderer now supports bounded appearance configuration for:
  - font family
  - body font size
  - page margins
  - compact vs cozy spacing
  - accent color

## Non-Goals

- reopening generic search-platform work
- adding a second canonical search or storage model
- turning this repo into a full OOXML authoring toolkit
- importing `docx-skill` wholesale without a bounded fit analysis

## Acceptance Criteria

- the current export surfaces are audited against this repo's OOXML/export goals
- a bounded DOCX/OOXML export target is chosen explicitly
- the expected reuse boundary with `docx-skill` is documented
- at least one implementation slice is identified clearly enough to execute next without reopening broad planning

## Next Implementation Slice

- add a bounded DOCX renderer for the channel/day JSON export artifact
- keep content assembly in `scripts/export_channel_day.py` and avoid a second SQLite-querying DOCX export path
- use minimal OOXML primitives first: document sections, speaker paragraphs, reply indentation, timestamp metadata, and attachment link blocks
- defer richer visual polish and multi-day composition until the single-day DOCX path is deterministic and testable

Current status:

- shipped through `scripts/export_channel_day_docx.py`
- paragraph-style and attachment-presentation hardening is now landed in the same renderer
- bounded multi-day composition is now landed through `scripts/export_multi_day_docx.py`
- semantic daypack DOCX output now composes through the same JSON-based renderer path
- structural DOCX export validation is now landed through `scripts/validate_export_docx.py`
- the validator now includes a first bounded reuse of `docx-skill` package-validation ideas without importing the whole skill
- renderer output is now compatible with the local LibreOffice render/vision QA path used by `docx-skill`
- bounded appearance configurability is now landed without turning the renderer into a general theme engine
- named fixture profiles are now part of the renderer QA contract:
  - `compact_default`
  - `cozy_review`
- a repo-local fixture artifact generator is now landed through `scripts/render_export_docx_fixtures.py`, producing canonical sample JSON, DOCX outputs, validator summaries, and rendered PDF/PNG review artifacts for the named fixture profiles
- the current renderer refinement pass now includes:
  - subtle paragraph shading for message/reply scanability
  - tighter sender metadata alignment
  - portable attachment-type badges
  - safer attachment-link selection that prefers explicit public/download URLs or Slack permalinks and treats local mirror paths as descriptive references instead of primary hyperlinks
- managed export bundling is now landed in `scripts/export_channel_day.py`, with:
  - config-backed user-scoped export roots
  - deterministic human-readable export IDs
  - copied attachment bundle paths
  - config-backed local/external `download_url` generation
  - portable `public_url` emission for downstream renderers
  - audience-keyed `download_urls` and `preview_urls` maps so one bundle can serve both local and external consumers
- the local API now serves bundle files under `/exports/<export-id>/<filepath>`
- the local API now exposes first-class export manifests under `/v1/exports` and `/v1/exports/<export-id>`, rebuilding current configured bundle URLs from live service config
- bounded preview routing is now landed under `/exports/<export-id>/<filepath>/preview` for:
  - images
  - PDFs
  - `.docx` through lightweight `mammoth` HTML conversion
  - `.pptx` through slide-by-slide HTML summary rendering
  - `.xlsx` through bounded sheet-table HTML summary rendering
  - `.odt` through bounded text-summary rendering
  - `.odp` through slide-by-slide HTML summary rendering
  - `.ods` through bounded sheet-table HTML summary rendering
  - text-like files
- unsupported binary types now fail explicitly with `PREVIEW_UNSUPPORTED`
- next likely slice is deeper OOXML primitive reuse or closure judgment, not more ad hoc render plumbing

## Definition Of Done

This plan is done when Slack Mirror has a narrow, actionable export-quality OOXML plan that is grounded in the repo's actual export scripts, has an explicit reuse boundary for `docx-skill`, and is ready for bounded implementation slices.
