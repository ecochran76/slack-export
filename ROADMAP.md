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

Current state:
- keyword and semantic search exist
- embedding backlog discipline and SQLite contention hardening have landed
- cross-repo comparison against `../ragmail` and `../imcli` established the modernization direction explicitly
- the shipped baseline now includes:
  - first-class `derived_text`, `derived_text_fts`, and `derived_text_jobs` tables
  - first-class `derived_text_chunks` and `derived_text_chunks_fts` tables for retrieval depth on long non-message documents
  - document-native extraction for canvases, UTF-8 text-like files, OOXML office files, and machine-readable PDFs when `pdftotext` is available
  - OCR extraction for image-like files and scanned PDFs when `tesseract` and `pdftoppm` are available
  - `search derived-text`, `search corpus`, and `mirror process-derived-text-jobs` operator surfaces
  - explicit cross-workspace corpus search through shared service, CLI, API, and MCP
  - API and MCP exposure for corpus search, readiness, and search health
  - shared search-health gates over readiness plus optional corpus smoke and depth benchmarks, with per-query diagnostics and bounded ranking-quality thresholds
- the modernization lane is closed on this SQLite-first shipped baseline; future search work should open narrower follow-up plans for additional extraction providers, ranking changes, or backend expansion rather than leaving `P03` generically open

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
