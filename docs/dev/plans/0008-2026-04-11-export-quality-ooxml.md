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
- the repo now has materially better OOXML extraction knowledge for search, especially for `.docx`, `.pptx`, and `.xlsx`
- `docx-skill` appears to contain reusable OOXML story/text primitives that could improve export fidelity, but that reuse has not yet been scoped for this repo
- the main gap is export quality, not search corpus shape

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

### Track B | OOXML Primitive Reuse

- identify the minimal `docx-skill` story/text/structure primitives that are useful here
- reuse only what helps deterministic export rendering or export QA
- avoid importing mutation, review, or authoring features that do not serve Slack export output

### Track C | Export Contract And QA

- define what a good DOCX-grade export means for this repo
- add bounded fixture-based validation for export output quality
- prefer render or structure checks that catch obvious formatting regressions

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

## Definition Of Done

This plan is done when Slack Mirror has a narrow, actionable export-quality OOXML plan that is grounded in the repo's actual export scripts, has an explicit reuse boundary for `docx-skill`, and is ready for bounded implementation slices.
