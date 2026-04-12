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
- next likely slice is deeper fixture quality or more ambitious OOXML primitive reuse, not a second export ownership path

## Definition Of Done

This plan is done when Slack Mirror has a narrow, actionable export-quality OOXML plan that is grounded in the repo's actual export scripts, has an explicit reuse boundary for `docx-skill`, and is ready for bounded implementation slices.
