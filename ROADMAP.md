# Slack Export Roadmap

This file is the master plan for repository-level priorities.

Planning rules:
- Revise this file cautiously.
- Do not materially reorder, rename, or reprioritize roadmap lanes unless the user explicitly asks for that change or a narrow correction is required to reflect already-requested work.
- Treat this file as the authoritative priority map.
- Treat `RUNBOOK.md` as the dated turn log of what happened.
- Treat actionable plan files under `docs/dev/plans/` as the bounded implementation plans.
- Keep closed lanes compact. Summarize shipped baseline and grouped child-plan coverage here; keep detailed slice-by-slice archaeology in the plan files and runbook.

## P01 | Platform Foundation

Status: CLOSED

Purpose:
- standardize one supported runtime topology
- standardize install/upgrade semantics
- standardize release and service-boundary planning

Actionable plans:
- `docs/dev/plans/0001-2026-04-09-platform-foundation.md`
- `docs/dev/plans/0002-2026-04-09-installer-upgrade-path.md`
- `docs/dev/plans/0040-2026-04-14-planning-contract-cleanup.md`
- `docs/dev/plans/0041-2026-04-14-runbook-monotonicity-and-git-hygiene.md`
- `docs/dev/plans/0042-2026-04-14-policy-adoption-and-migration.md`
- `docs/dev/plans/0043-2026-04-14-legacy-runbook-retirement.md`
- `docs/dev/plans/0044-2026-04-14-policy-surface-fit-trim.md`
- `docs/dev/plans/0045-2026-04-14-agents-thin-entrypoint.md`
- `docs/dev/plans/0046-2026-04-14-policy-module-localization.md`

Current state:
- supported live topology is documented as socket-mode ingress plus one unified daemon per workspace
- user-scope install and update flows exist
- bounded user-scope rollback exists
- release/version discipline now has a supported `slack-mirror release check` gate with an explicit release-cut procedure
- planning governance now explicitly keeps closed-lane summaries compact, with detailed slice archaeology left to the runbook and plan files
- runbook governance now explicitly requires monotonic turn numbering in file order, not only globally unique headings
- shared durable repo policy is now adopted under `docs/dev/policies/`, with `AGENTS.md` acting as the repo-local policy-loading entrypoint
- the adopted policy surface is now intentionally trimmed to the modules this repo actually uses, instead of keeping the entire generic selector recommendation as dead weight
- `AGENTS.md` is now thinned back to a repo-local routing surface instead of duplicating large portions of the retained durable policy body
- the remaining retained policy modules are now localized to this repo's actual upgrade and feedback workflow instead of generic shared-library defaults
- the legacy `docs/dev/RUNBOOK.md` continuity log has been retired from canonical authority and preserved under `docs/dev/legacy/` so selector-based policy audits no longer see duplicate runbook authorities
- the coordinating platform-foundation lane is closed; remaining work proceeds through narrower lanes such as `P02` and future bounded child plans when needed

Legacy context:
- retained through the dated runbook and prior local planning notes when needed for archaeology

## P02 | Service Surfaces

Status: CLOSED

Purpose:
- define and harden the shared application boundary for CLI, API, MCP, and skills

Actionable plans:
- shared service/API/MCP boundary: `docs/dev/plans/0003-2026-04-09-api-mcp-boundary.md`
- browser auth and account governance: `docs/dev/plans/0009-2026-04-13-frontend-auth-baseline.md`, `docs/dev/plans/0010-2026-04-13-frontend-auth-hardening.md`, `docs/dev/plans/0011-2026-04-13-frontend-auth-idle-timeout.md`, `docs/dev/plans/0012-2026-04-13-frontend-auth-settings-governance.md`, `docs/dev/plans/0013-2026-04-13-frontend-auth-live-defaults.md`, `docs/dev/plans/0014-2026-04-13-frontend-auth-bootstrap-provisioning.md`
- report/export browser management baseline: `docs/dev/plans/0015-2026-04-13-report-export-crud.md`, `docs/dev/plans/0016-2026-04-13-frontend-report-export-manager.md`, `docs/dev/plans/0017-2026-04-13-frontend-export-choice-picker.md`, `docs/dev/plans/0018-2026-04-13-frontend-report-choice-presets.md`, `docs/dev/plans/0019-2026-04-13-frontend-export-channel-filter.md`, `docs/dev/plans/0020-2026-04-13-frontend-export-inline-rename.md`, `docs/dev/plans/0021-2026-04-13-frontend-export-inline-mutation-state.md`, `docs/dev/plans/0022-2026-04-13-frontend-report-inline-mutation-state.md`, `docs/dev/plans/0023-2026-04-14-frontend-report-inline-create.md`, `docs/dev/plans/0024-2026-04-14-frontend-export-inline-create.md`
- browser UX hardening and maintainability follow-ups: `docs/dev/plans/0025-2026-04-14-frontend-inline-manager-helper-consolidation.md`, `docs/dev/plans/0026-2026-04-14-frontend-manager-empty-state-restoration.md`, `docs/dev/plans/0027-2026-04-14-runtime-report-create-auth-safe.md`, `docs/dev/plans/0028-2026-04-14-managed-export-script-packaging.md`, `docs/dev/plans/0029-2026-04-14-frontend-inline-mutation-busy-state.md`, `docs/dev/plans/0030-2026-04-14-frontend-inline-create-busy-state.md`, `docs/dev/plans/0031-2026-04-14-frontend-busy-labels.md`, `docs/dev/plans/0032-2026-04-14-frontend-row-local-errors.md`, `docs/dev/plans/0033-2026-04-14-frontend-create-local-errors.md`, `docs/dev/plans/0034-2026-04-14-frontend-create-validation.md`, `docs/dev/plans/0035-2026-04-14-frontend-invalid-field-styling.md`, `docs/dev/plans/0036-2026-04-14-frontend-create-accessibility-focus.md`, `docs/dev/plans/0037-2026-04-14-frontend-field-level-create-errors.md`, `docs/dev/plans/0038-2026-04-14-frontend-create-helper-consolidation.md`, `docs/dev/plans/0039-2026-04-14-frontend-row-state-chips.md`

Current state:
- shared application-service layer exists
- local API server exists
- MCP server exists
- shared machine-readable success and error contracts are documented and enforced across service, API, and MCP
- outbound write, listener, and live-validation semantics now run through one explicit shared boundary
- browser auth baseline is shipped, including protected browser routes, local password sessions, same-origin browser writes, idle timeout, login throttling, visible auth-policy display, closed-by-default self-registration, and first-user bootstrap plus password rotation through `user-env provision-frontend-user`
- report/export management baseline is shipped through the shared service/API boundary, including browser CRUD on `/runtime/reports` and `/exports`, channel-choice loading, presets, inline rename/delete/create, and managed-export script packaging for installed user environments
- browser interaction hardening is shipped, including busy-state protection, busy labels, row-local and form-local errors, client-side create validation, invalid-field styling, first-invalid focus, field-level helper/error text, shared helper consolidation, and compact per-row mutation outcome chips
- `P02` is now closed; any future browser-auth or broader service-surface work should open a new narrow child plan instead of reopening the full lane

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
- the shipped baseline now includes first-class derived-text and chunk tables, lexical-first corpus search over messages plus derived text, OCR and document-native extraction for the current supported file families, explicit cross-workspace corpus search, and shared readiness/search-health gates across CLI, API, and MCP
- the extraction-provider boundary is landed, with the current host-local toolchain retained as the default implementation and command-backed plus HTTP-backed providers available behind the same contract
- `docx-skill` is a likely source of reusable OOXML primitives for both richer `.docx` extraction and future DOCX-quality export rendering
- the export-quality follow-up under `0008` is also landed on the current baseline: channel/day JSON is the canonical export artifact, DOCX-quality rendering exists on top of it, managed export bundles and API-served manifests are first-class, and lightweight in-browser previews cover OOXML plus OpenDocument files without requiring a full office server
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

## P06 | Browser Search And Frontend Hardening

Status: CLOSED

Purpose:
- introduce a first-class authenticated browser search surface over the shipped search APIs
- harden browser-side query, result, and operator-context behavior without reopening the broader service or search lanes

Actionable plans:
- `docs/dev/plans/0047-2026-04-14-frontend-search-surface-and-hardening.md`

Current state:
- the browser already has authenticated management surfaces for landing, settings, runtime reports, and exports
- the browser now also has an authenticated `/search` surface over the existing corpus-search and readiness APIs
- the shipped browser search baseline includes URL-backed state, workspace/all-workspace scope, mode and derived-text filters, bounded pagination with `offset` plus total-result counts, duplicate-submit protection, inline readiness context for one-workspace searches, refinement links from result cards, stable repo-owned JSON detail destinations for message and derived-text hits, shared low-level browser helpers reused across the existing authenticated manager pages, shared fetch/error helpers for bounded browser-side request plumbing, and shared authenticated topbar rendering across `/`, `/settings`, and `/search`
- the live managed install has been refreshed from the current repo and browser QA passed on `/`, `/settings`, `/search`, `/runtime/reports`, and `/exports`
- deferred follow-ups such as a browser-native viewer or broader frontend extraction should open as separate bounded slices if they are ever justified
