# Slack Export Roadmap

This file is the master plan for repository-level priorities.

Planning rules:
- Revise this file cautiously.
- Do not materially reorder, rename, or reprioritize roadmap lanes unless the user explicitly asks for that change or a narrow correction is required to reflect already-requested work.
- Treat this file as the authoritative priority map.
- Treat `RUNBOOK.md` as the dated turn log of what happened.
- Treat actionable plan files under `docs/dev/plans/` as the bounded implementation plans.

## P01 | Platform Foundation

Status: CLOSED

Purpose:
- standardize one supported runtime topology
- standardize install/upgrade semantics
- standardize release and service-boundary planning

Actionable plans:
- `docs/dev/plans/0001-2026-04-09-platform-foundation.md`
- `docs/dev/plans/0002-2026-04-09-installer-upgrade-path.md`

Current state:
- supported live topology is documented as socket-mode ingress plus one unified daemon per workspace
- user-scope install and update flows exist
- bounded user-scope rollback exists
- release/version discipline now has a supported `slack-mirror release check` gate with an explicit release-cut procedure
- the coordinating platform-foundation lane is closed; remaining work proceeds through narrower lanes such as `P02` and future bounded child plans when needed

Legacy context:
- retained through the dated runbook and prior local planning notes when needed for archaeology

## P02 | Service Surfaces

Status: CLOSED

Purpose:
- define and harden the shared application boundary for CLI, API, MCP, and skills

Actionable plans:
- `docs/dev/plans/0003-2026-04-09-api-mcp-boundary.md`

Current state:
- shared application-service layer exists
- local API server exists
- MCP server exists
- shared machine-readable success and error contracts are documented and enforced across service, API, and MCP
- outbound write, listener, and live-validation semantics now run through one explicit shared boundary
- the baseline service-surface lane is closed; future surface work should open narrower follow-up plans instead of keeping `P02` generically open

Legacy context:
- retained through the dated runbook and prior local planning notes when needed for archaeology

## P03 | Search And Evaluation

Status: CLOSED

Purpose:
- keep search, evaluation, and search-platform reuse on a bounded roadmap lane

Actionable plans:
- `docs/dev/plans/0006-2026-04-11-search-evaluation-modernization.md`
- `docs/dev/plans/0007-2026-04-11-extraction-provider-expansion.md`
- `docs/dev/plans/0008-2026-04-11-export-quality-ooxml.md`

Current state:
- keyword and semantic search exist
- embedding backlog discipline and SQLite contention hardening have landed
- cross-repo comparison against `../ragmail` and `../imcli` established the modernization direction explicitly
- the shipped baseline now includes:
  - first-class `derived_text`, `derived_text_fts`, and `derived_text_jobs` tables
  - first-class `derived_text_chunks` and `derived_text_chunks_fts` tables for retrieval depth on long non-message documents
  - document-native extraction for canvases, UTF-8 text-like files, OOXML and OpenDocument office files, with story-aware `.docx` extraction, visible-text-aware `.pptx` extraction, shared-string-aware `.xlsx` extraction, and machine-readable PDFs when `pdftotext` is available
  - OCR extraction for image-like files and scanned PDFs when `tesseract` and `pdftoppm` are available
  - `search derived-text`, `search corpus`, and `mirror process-derived-text-jobs` operator surfaces
  - explicit cross-workspace corpus search through shared service, CLI, API, and MCP
  - API and MCP exposure for corpus search, readiness, and search health
  - shared search-health gates over readiness plus optional corpus smoke and depth benchmarks, with per-query diagnostics and bounded ranking-quality thresholds
- active follow-up scope is now narrower:
  - the extraction-provider boundary is landed, with the current host-local toolchain retained as the default implementation
  - command-backed and HTTP-backed providers are landed, with local fallback retained by default
  - extraction outcome thresholding is landed on top of readiness reporting and search health
  - broader document-format coverage now includes OOXML and OpenDocument office files where they fit the shared `derived_text` contract cleanly
- `docx-skill` is a likely source of reusable OOXML primitives for both richer `.docx` extraction and future DOCX-quality export rendering
- active follow-up scope is now narrowed again through `0008`, which is focused on export-quality OOXML work rather than reopening generic search modernization
- the current `0008` decision is to make channel/day export the first DOCX-quality target, with multi-day and semantic daypack outputs composing on top of that same artifact
- the first implementation slice under `0008` is a bounded DOCX renderer over the existing channel/day JSON export artifact
- the current `0008` quality pass is improving paragraph/run formatting and attachment presentation within that same renderer rather than adding a second export path
- repeatable DOCX export review artifacts are now generated through a repo-local fixture script instead of one-off manual render commands
- managed export bundles and API-served `/exports/<export-id>/<filepath>` download URLs are now part of the active export-quality baseline
- the live service now exposes first-class export manifests through `/v1/exports` and `/v1/exports/<export-id>`, rebuilding configured local/external bundle URLs instead of leaving the published export contract entirely script-owned
- bounded in-browser previews now cover `.docx`, `.pptx`, and `.xlsx` through lightweight conversion paths rather than a full office-server dependency
- bounded in-browser previews now cover the OpenDocument office set as well (`.odt`, `.odp`, `.ods`) through the same lightweight extraction-first architecture
- `P03` is now closed; future search or export follow-up work should open a new narrow child plan instead of reopening the broad modernization lane

Legacy context:
- `docs/dev/PHASE_E_SEMANTIC_SEARCH.md`
- `docs/dev/PHASE_F_SEARCH_PLATFORM.md`
- `docs/dev/SEARCH_EVAL.md`
- `docs/dev/DAILY_BRIEFING_HARDENING_PLAN.md`

## P04 | Live Ops And Runtime Hardening

Status: CLOSED

Purpose:
- keep live-mode operations, auth guardrails, user install, and daemon drift checks coherent

Actionable plans:
- `docs/dev/plans/0005-2026-04-10-live-ops-runtime-hardening.md`

Current state:
- supported live topology is documented
- install/status scripts exist
- auth guardrails and explicit outbound validation exist
- live validation, smoke-check, and bounded recovery flows now define the supported unattended operator contract
- queue backlog, queue errors, duplicate topology, inactive units, and stale mirror freshness are all surfaced through supported status paths
- restart-only remediations are supported automatically, while config/token/DB/topology cleanup remains explicitly operator-owned

Legacy context:
- `docs/dev/LIVE_MODE.md`
- `docs/dev/AUTH_GUARDRAILS.md`
- `docs/dev/USER_INSTALL.md`

## P05 | Outbound Messaging And Listeners

Status: CLOSED

Purpose:
- make outbound messaging and listener/hook workflows first-class platform capabilities

Actionable plans:
- `docs/dev/plans/0004-2026-04-09-outbound-listeners-hardening.md`

Current state:
- outbound send and thread-reply flows exist through the shared service
- listener registration, delivery inspection, and delivery acknowledgement exist
- the outbound/listener contract is now documented and enforced across service, API, and MCP surfaces
- the current local queue-delivery model is the supported baseline unless future requirements justify richer retry policy
