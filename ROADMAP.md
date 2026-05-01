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

## P07 | Install Onboarding And Manifest Hardening

Status: CLOSED

Purpose:
- make new-user installation and first-workspace onboarding well explained, fast, and low-friction
- harden the emitted JSON manifests so onboarding and downstream tooling can rely on them as real contracts

Actionable plans:
- `docs/dev/plans/0048-2026-04-15-install-onboarding-and-manifest-hardening.md`

Current state:
- user-scope install/update/live-validation flows already exist, but the operator journey is split across install, config, live-mode, auth-bootstrap, and contract docs
- the docs-first onboarding baseline is now shipped: `docs/dev/USER_INSTALL.md` is the canonical fresh-install-to-first-workspace path, and `README.md`, `docs/CONFIG.md`, and `docs/dev/LIVE_MODE.md` now route operators into that same sequence instead of leaving them to stitch the flow together manually
- manifest hardening is now also shipped: export and runtime-report JSON manifests carry explicit schema, generation-time, producer, and provenance metadata, runtime reports expose compact machine-readable validation summary fields, and `docs/API_MCP_CONTRACT.md` documents the exact route shapes
- the cold-path docs rehearsal is complete: onboarding docs now distinguish repo-side `uv run slack-mirror ...` commands before install from managed `slack-mirror-user ...` commands after install
- `P07` is closed; a real clean-user live Slack credential rehearsal should open a new explicit ops slice if needed

## P08 | Polymer Tenant Onboarding

Status: OPEN

Purpose:
- onboard Polymer Consulting Group as a new Slack Mirror workspace/tenant without destabilizing existing live workspaces
- use the new onboarding path against a real tenant while keeping credentials and activation explicit

Actionable plans:
- `docs/dev/plans/0049-2026-04-15-polymer-tenant-onboarding.md`

Current state:
- Polymer is scaffolded in the managed config as disabled with explicit `SLACK_POLYMER_*` credential placeholders
- the disabled Polymer workspace has been synced into the managed DB
- current active workspace validation still passes for `default` and `soylei`
- repo code and the managed install now skip disabled workspace scaffolds during default `workspaces verify`, matching live-validation behavior
- explicit verification reports Polymer as disabled until credentials are available and the workspace is activated
- activation is blocked on Polymer Slack credentials

## P09 | Tenant Onboarding Wizard And Settings

Status: OPEN

Purpose:
- make new tenant/workspace setup a guided product workflow instead of a manual sequence spread across docs, config editing, Slack app setup, dotenv storage, DB sync, systemd scripts, and validation commands
- expose tenant management and onboarding state in the authenticated browser settings surface

Actionable plans:
- `docs/dev/plans/0050-2026-04-15-tenant-onboarding-wizard-and-settings.md`
- `docs/dev/plans/0051-2026-04-18-operator-frontend-reuse-architecture.md`
- `docs/dev/plans/0096-2026-04-21-frontend-selected-result-contract-model.md`
- `docs/dev/plans/0097-2026-04-21-frontend-app-shell-scaffold.md`
- `docs/dev/plans/0098-2026-04-21-operator-frontend-preview-route.md`
- `docs/dev/plans/0099-2026-04-21-react-tenant-status-adapter.md`
- `docs/dev/plans/0100-2026-04-21-react-tenant-workbench-browser-qa.md`
- `docs/dev/plans/0101-2026-04-21-react-tenant-detail-expansion.md`
- `docs/dev/plans/0102-2026-04-21-react-tenant-density-view-toggle.md`
- `docs/dev/plans/0103-2026-04-21-neutral-status-widget-primitive.md`
- `docs/dev/plans/0104-2026-04-21-neutral-entity-table-primitive.md`
- `docs/dev/plans/0105-2026-04-21-neutral-view-toggle-primitive.md`
- `docs/dev/plans/0106-2026-04-21-neutral-detail-panel-primitive.md`
- `docs/dev/plans/0107-2026-04-21-neutral-action-button-group-primitive.md`
- `docs/dev/plans/0108-2026-04-22-neutral-refresh-status-primitive.md`
- `docs/dev/plans/0109-2026-04-22-react-initial-sync-mutation.md`
- `docs/dev/plans/0110-2026-04-22-react-start-live-sync-mutation.md`
- `docs/dev/plans/0111-2026-04-22-react-restart-live-sync-mutation.md`
- `docs/dev/plans/0112-2026-04-22-neutral-confirm-dialog-primitive.md`
- `docs/dev/plans/0113-2026-04-22-react-stop-live-sync-mutation.md`
- `docs/dev/plans/0114-2026-04-22-frontend-tracked-mutation-helper.md`
- `docs/dev/plans/0115-2026-04-22-react-activate-tenant-mutation.md`
- `docs/dev/plans/0116-2026-04-22-react-credential-install-form.md`
- `docs/dev/plans/0117-2026-04-22-react-tenant-retire-mutation.md`
- `docs/dev/plans/0118-2026-04-22-react-maintenance-backfill-mutation.md`
- `docs/dev/plans/0119-2026-04-22-react-tenant-action-browser-qa.md`
- `docs/dev/plans/0120-2026-04-22-react-action-ergonomics-polish.md`

Current state:
- shared tenant onboarding primitives now expose redacted status, disabled scaffold creation, credential installation, activation, live-sync controls, bounded backfill, and guarded retirement over CLI and protected API routes
- `slack-mirror-user tenants onboard`, `tenants credentials`, `tenants status`, `tenants activate`, `tenants live`, `tenants backfill`, and `tenants retire` are now the product-owned add-workspace and tenant-management path
- `/settings/tenants` now exposes config-backed tenant status, scaffold creation, local credential installation, credential-ready activation, live sync start/restart/stop, bounded backfill, and guarded retirement in the authenticated browser
- credential installation writes only to the configured dotenv file, backs it up when changed, and never echoes secret values in status/API output
- the current browser tenant surface is still a Python-rendered inline-HTML/JS page, which is sufficient for the shipped baseline but is now a poor fit for the denser operator-console UX the product needs next
- the next frontend direction is now explicitly cross-repo:
  - `slack-export`, `../imcli`, and `../ragmail` all need the same class of operator console
  - reuse should be designed around shared operator-shell, status-widget, table/row, and theming primitives rather than a Slack-shaped one-off browser rewrite
- remaining work is now split into:
  - a real credential-backed Polymer activation rehearsal
  - tenant-status and control UX refinement driven by live operator feedback
  - a dedicated frontend-app migration for the tenant operator surface, with React/Vite-style client architecture preferred over extending the current inline page indefinitely

Frontend subprojects for the operator-console migration:
- shell and navigation:
  - shared app shell, account/avatar chip placement, top bar, collapsible side rail, context selectors, and route framing
- theme and design system:
  - token contract, density modes, semantic status variants, typography, spacing, motion, and theme swapping without behavior changes
- entity-management workbench:
  - dense table or row views for tenants, sources, and managed entities, with status widgets, metric strips, inline actions, expandable details, and maintenance controls
- search workbench:
  - advanced search controls, saved views, facet and query-builder patterns, result grouping, row selection, candidate staging, and bulk actions
- report and artifact pipeline:
  - report generation, export flows, result-to-report handoff, artifact history, rename/delete/create, and bounded operator publishing workflows
- logs and runtime observability:
  - live and recent logs, runtime health summaries, queue and backfill state, poll-first status refresh, and later streaming follow-up only if justified
- repo-local adapters and API binding:
  - thin repo-specific API clients and data mappers that bind shared operator UI primitives to Slack, messaging, and email backends without making the shared layer transport-specific

Planned slice order inside `P09`:
1. architecture and package-boundary definition through `0051`
2. shell, theme, and shared operator primitives
3. `/settings/tenants` migration as the first proving workbench
4. search-workbench migration and result-selection model
5. report/artifact workflow migration
6. logs/runtime observability refinement

Cross-repo convergence refinement:
- the shared operator-console direction should now explicitly align with a
  broader communications-corpus convergence path across `slack-export`,
  `../imcli`, and `../ragmail`
- the first shared UI extraction should wait until selected-result
  export/report contracts are stable enough that search results, context
  windows, export bundles, and report artifacts can be represented without
  Slack-only naming
- `slack-export` should continue to prove the frontend patterns locally, but
  avoid hardcoding future shared components around Slack-specific nouns such as
  workspace, channel, or thread timestamp when neutral source, conversation,
  thread, message, participant, attachment, and action-target terminology would
  fit
- the selected-result workflow is now stable enough to seed the first frontend
  contract model, completed under `0096`:
  - `frontend/src/contracts/selectedResults.ts` defines provider-neutral
    selected target, candidate, context, artifact, and report-view action types
  - `docs/dev/FRONTEND_CONTRACTS.md` records Slack-to-neutral mapping and the
    shared-vs-repo-local adapter boundary
- the first Vite/React/TypeScript app shell scaffold is complete under `0097`:
  - `frontend/package.json` owns frontend `dev`, `typecheck`, `build`, and
    `preview` commands
  - `frontend/src/components/OperatorShell.tsx` and theme token files establish
    the initial shell/navigation/account-chip and theme boundary
  - the first screen is static and contract-driven; live API adapters and Python
    service asset wiring remain later child slices
- the Python service now serves the built React preview under `/operator`,
  completed under `0098`, while keeping existing Python-rendered pages as the
  production operator surfaces until parity is reached
- the React preview now has its first live read-only adapter under `0099`:
  - `/operator` fetches `/v1/tenants` with same-origin credentials
  - tenant rows render DB stats, backfill status, live status, health, next
    action, and semantic readiness
  - tenant mutations still route to `/settings/tenants` until React parity is
    intentionally reached
- browser QA against the worktree-served `/operator` preview completed under
  `0100`, fixing the stale shell title and long status-chip wrapping found in
  the first screenshot
- tenant-row density polish is complete under `0101`, keeping identity, DB
  stats, backfill, live-sync, and health visible while moving lower-frequency
  live-unit, text/embedding, and semantic-readiness diagnostics behind an
  accessible per-tenant disclosure
- the React tenant workbench now includes a read-only density toggle under
  `0102`, preserving the card view while adding a compact table view for
  scanning tenant readiness, DB stats, live/backfill/health state, semantic
  readiness, and expandable diagnostics
- the first neutral status-widget primitive is complete under `0103`, giving
  the React workbench reusable `StatusBadge` and `StatusPanel` components while
  keeping Slack-specific tone and label mapping inside the local tenant adapter
  for later `../imcli` and `../ragmail` convergence
- the first neutral entity-table primitive is complete under `0104`, moving
  table shell, row-key, row-header, and column rendering mechanics into
  `EntityTable` while leaving Slack tenant columns and API mapping local
- the first neutral view-toggle primitive is complete under `0105`, moving the
  card/table density switch into `ViewToggle` while keeping tenant-specific
  view meanings inside the local workbench
- the first neutral detail-panel primitive is complete under `0106`, moving
  card and compact-table diagnostics disclosures into `DetailPanel` while
  keeping Slack-specific live-unit, text/embedding, and semantic-readiness
  content inside the tenant workbench
- the first neutral action-button-group primitive is complete under `0107`,
  rendering status-derived but disabled recommended tenant actions while actual
  mutations remain on the production tenant settings surface
- the first neutral refresh-status primitive is complete under `0108`, exposing
  tenant status freshness, polling interval, and manual refresh affordance while
  keeping API fetch and polling policy inside the tenant adapter
- the first React tenant mutation is complete under `0109`, enabling only
  `Run initial sync` against the existing bounded tenant backfill API with
  immediate busy/success/error feedback and post-command status refresh
- the second narrow React tenant mutation is complete under `0110`, enabling
  only `Start live sync` for explicit `start_live_sync` next-action status
  against the existing tenant live API while restart/stop remain disabled
- the third narrow React tenant mutation is complete under `0111`, enabling
  `Restart live sync` only as a degraded-active-unit recovery action while
  `Stop live sync` remains blocked on an explicit confirmation pattern
- the neutral confirmation-dialog primitive is complete under `0112`, with a
  non-mutating tenant-workbench preview proving typed confirmation before any
  destructive `Stop live sync` wiring
- the destructive `Stop live sync` mutation is complete under `0113`, requiring
  typed tenant-name confirmation before posting the existing stop action and
  refreshing tenant status
- the local tracked-mutation helper is complete under `0114`, consolidating
  keyed busy/success/error/refresh mechanics without moving Slack-specific
  routes, payloads, or action semantics into shared UI primitives
- the React `Activate tenant` mutation is complete under `0115`, enabling only
  `ready_to_activate` tenants and mirroring the production one-click sequence:
  activate, install live sync, then start bounded initial sync
- the React credential-install form is complete under `0116`, enabling
  missing-credential tenants to submit non-empty Slack credential fields to the
  existing redacting credentials API without storing secrets in React state
- the React tenant-retirement mutation is complete under `0117`, exposing
  typed-confirmation retirement only for non-protected tenants and preserving
  the explicit optional mirrored-DB deletion choice
- the React maintenance-backfill mutation is complete under `0118`, exposing a
  bounded backfill maintenance action for enabled synced tenants that are not
  already in initial-sync or syncing state
- authenticated browser QA of the React tenant action surface is complete under
  `0119`: current tenants render in card/table views, protected tenants hide
  retirement, non-protected retirement and stop-live actions require typed
  confirmation, and desktop/mobile layouts avoid page-level horizontal overflow
- tenant action ergonomics polish is complete under `0120`: action affordances
  are grouped by neutral intent, guarded stop/retire controls are visually
  separated from maintenance work, and the compact table allocates more room to
  the details affordance

## P10 | Semantic Retrieval And Relevance Hardening

Status: OPEN

Purpose:
- upgrade the current basic local semantic-search baseline into a real retrieval stack that better serves messages, attachments, OCR text, and corpus-wide search
- build on the shipped `v0.2.0` MCP-capable user-scoped baseline with relevance, rollout, and local-inference improvements that remain explicitly opt-in until proven

Actionable plans:
- `docs/dev/plans/0053-2026-04-19-semantic-provider-and-model-seam-hardening.md`
- `docs/dev/plans/0054-2026-04-19-local-semantic-retrieval-architecture.md`
- `docs/dev/plans/0055-2026-04-19-bge-m3-message-embeddings.md`
- `docs/dev/plans/0056-2026-04-19-bge-m3-readiness-and-evaluation.md`
- `docs/dev/plans/0057-2026-04-19-bge-m3-bounded-live-rehearsal.md`
- `docs/dev/plans/0058-2026-04-19-bge-m3-bounded-message-rollout.md`
- `docs/dev/plans/0059-2026-04-19-derived-text-chunk-embeddings.md`
- `docs/dev/plans/0060-2026-04-19-derived-text-retrieval-evaluation.md`
- `docs/dev/plans/0061-2026-04-19-reranker-provider-seam.md`
- `docs/dev/plans/0062-2026-04-19-learned-local-reranker-provider.md`
- `docs/dev/plans/0063-2026-04-19-learned-reranker-live-rehearsal.md`
- `docs/dev/plans/0064-2026-04-19-semantic-retrieval-profiles-rollout-controls.md`
- `docs/dev/plans/0065-2026-04-19-tenant-semantic-readiness-diagnostics.md`
- `docs/dev/plans/0066-2026-04-19-query-fusion-and-explainability-hardening.md`
- `docs/dev/plans/0067-2026-04-19-actionable-search-results.md`
- `docs/dev/plans/0068-2026-04-20-scale-and-inference-boundary-review.md`
- `docs/dev/plans/0069-2026-04-20-release-profile-and-semantic-search-policy.md`
- `docs/dev/plans/0074-2026-04-20-mcp-retrieval-profile-search.md`
- `docs/dev/plans/0075-2026-04-20-default-search-backlog-drain.md`
- `docs/dev/plans/0076-2026-04-20-managed-local-bge-rollout-rehearsal.md`
- `docs/dev/plans/0077-2026-04-20-semantic-query-performance-cap.md`
- `docs/dev/plans/0078-2026-04-20-local-inference-service-boundary.md`
- `docs/dev/plans/0079-2026-04-20-http-backed-bge-profile-rehearsal.md`
- `docs/dev/plans/0080-2026-04-20-live-relevance-benchmark-lock.md`
- `docs/dev/plans/0081-2026-04-21-noncontent-relevance-benchmark-pack.md`
- `docs/dev/plans/0082-2026-04-21-benchmark-target-bge-backfill.md`
- `docs/dev/plans/0084-2026-04-21-profile-aware-benchmark-diagnostics.md`
- `docs/dev/plans/0085-2026-04-21-benchmark-fusion-experiment.md`
- `docs/dev/plans/0086-2026-04-21-benchmark-query-variants.md`
- `docs/dev/plans/0087-2026-04-21-portable-query-date-operators.md`
- `docs/dev/plans/0088-2026-04-21-litscout-informed-attachment-query-operators.md`
- `docs/dev/plans/0089-2026-04-21-message-file-linkage-for-attachment-filters.md`
- `docs/dev/plans/0090-2026-04-21-selected-result-context-packs.md`
- `docs/dev/plans/0091-2026-04-21-selected-result-export-artifacts.md`
- `docs/dev/plans/0092-2026-04-21-selected-result-report-viewer.md`
- `docs/dev/plans/0093-2026-04-21-browser-selected-result-report-creation.md`
- `docs/dev/plans/0094-2026-04-21-browser-selected-result-bulk-affordances.md`
- `docs/dev/plans/0095-2026-04-21-selected-result-report-polish.md`
- `docs/dev/plans/0083-2026-04-21-cross-corpus-export-convergence.md`
- `docs/dev/plans/0135-2026-04-28-source-label-candidate-generation.md`
- `docs/dev/plans/0136-2026-04-28-domain-alias-candidate-generation.md`
- `docs/dev/plans/0137-2026-04-28-source-intent-ranking-priors.md`
- `docs/dev/plans/0138-2026-04-28-corpus-source-diversity-ordering.md`
- `docs/dev/plans/0139-2026-04-28-benchmark-row-level-metrics.md`
- `docs/dev/plans/0140-2026-04-28-lexical-coverage-rank-quality.md`
- `docs/dev/plans/0141-2026-04-28-benchmark-target-evidence-diagnostics.md`

Current state:
- the repo already has lexical, semantic, and hybrid search, plus first-class derived-text and chunk storage
- the first enabling slice is now complete under `0053`: one shared embedding-provider seam owns the shipped `local-hash-128` baseline across sync-time and query-time semantic paths
- the next implementation slice is now also complete under `0055`: message embedding jobs and message-backed corpus search can resolve through either the built-in `local_hash` baseline or an optional provider-routed `sentence_transformers` path for models such as `BAAI/bge-m3`
- the current default semantic baseline still uses the lightweight local `local-hash-128` path until a stronger local model is deliberately configured
- the next bounded slice is now focused on readiness and truthful evaluation:
  - repo-owned provider probing
  - GPU/runtime visibility
  - making the benchmark path actually exercise the configured message embedding provider
- that readiness/evaluation slice is now complete under `0056`, so the lane has:
  - an optional `local-semantic` dependency group
  - a repo-owned provider probe
  - truthful provider-aware benchmark plumbing
- the local workstation has now been validated as capable of a `BAAI/bge-m3` CUDA path once the optional semantic extra is installed
- the immediate next step is a bounded live-data rehearsal on a temporary DB copy so `bge-m3` quality can be judged on real paraphrase queries before any broader rollout
- that bounded live-data rehearsal is now complete under `0057` and the result is favorable:
  - `local-hash-128` missed all three bounded paraphrase targets
  - `bge-m3` hit all three within the top 3 on the rehearsal set
- the next implementation-critical step is no longer “is `bge-m3` viable,” but “how do we broaden bounded `bge-m3` message rollout safely and make that evaluation path repeatable”
- that bounded rollout slice is now complete under `0058`:
  - `mirror embeddings-backfill` can now target bounded message subsets directly
  - readiness and health now distinguish total embeddings from configured-model coverage
  - partial configured-model rollout now surfaces as an explicit warning instead of silently looking complete
- that next bounded slice is now also complete under `0059`:
  - derived-text chunk embeddings are now persisted per chunk and model id
  - semantic derived-text search now prefers stored chunk vectors under the configured provider/model seam
  - bounded rollout now exists for existing derived-text rows and for newly extracted rows during derived-text job processing
  - readiness and health now expose configured-model chunk coverage for both `attachment_text` and `ocr_text`
- that next bounded slice is now also complete under `0060`:
  - the shared eval harness now supports explicit derived-text benchmark evaluation
  - `search health` now supports a `derived_text` benchmark target while preserving corpus as the default
  - derived-text benchmark query reports now include chunk-aware debug output
- that next bounded slice is now also complete under `0061`:
  - reranking now sits behind a shared provider seam
  - the existing heuristic reranker remains the shipped baseline
  - corpus search can now opt into bounded reranking over fused message plus derived-text candidates through CLI, API, and MCP
- the default optional reranking path is still heuristic rescoring; learned reranking remains explicitly configured and experimental
- attachment and derived-text retrieval now exist, which raises the value of higher-quality local embeddings and reranking substantially
- the preferred direction for this lane is local-first rather than hosted-first, with the user's RTX 5080-class workstation making stronger local retrieval models practical
- the first stable MCP-capable release work under `P11` is now good enough that this lane has moved from seam hardening into architecture and the first real message-model path
- the live audit on 2026-04-19 shows the current lexical path is serviceable for exact-match retrieval, while semantic and hybrid paraphrase behavior are poor enough that stronger local retrieval is now an active product need
- derived-text retrieval is structurally present, but live coverage is still sparse to absent in current workspaces, which makes architecture-first rollout preferable to jumping straight into a model swap
- that next bounded slice is now also complete under `0062`:
  - optional learned local reranking is available through a `sentence_transformers` CrossEncoder provider
  - `search reranker-probe` reports dependency/GPU readiness and optional smoke scoring before use
  - default reranking remains heuristic unless config explicitly selects the learned provider
- the next implementation-critical step is a bounded live-data learned-reranker rehearsal against real tenant search queries, then benchmark threshold tuning if quality improves
- that rehearsal is now complete under `0063`:
  - learned reranking is technically viable on the RTX 5080 workstation
  - cold model warmup is expensive and warm query latency varies by candidate/text size
  - top-1 did not improve on the bounded live-message query set
  - learned reranking should remain experimental until stronger semantic rollout controls and labeled benchmarks exist
- the rollout-control slice is now complete under `0064`:
  - named retrieval profiles now distinguish `baseline`, `local-bge`, and experimental `local-bge-rerank`
  - corpus search, provider probes, reranker probes, and bounded embedding backfills can use profile-aware provider/model config explicitly
  - `mirror rollout-plan` is a read-only tenant coverage and command-planning surface for message and derived-text chunk rollout
- the tenant-readiness diagnostics slice is now complete under `0065`:
  - CLI, API, MCP, and the authenticated tenant settings page can report semantic readiness for named retrieval profiles
  - tenant readiness now distinguishes ready profiles, partial rollout, missing rollout, and unavailable providers without running backfills automatically
  - the current managed default workspace is baseline-current after the bounded catch-up in `0066`, while `local-bge` still needs rollout
- the query-fusion and explainability slice is now complete under `0066`:
  - corpus hybrid search preserves weighted fusion as the default
  - opt-in reciprocal-rank fusion is available through CLI, API, MCP, and the shared service boundary
  - corpus results include stable `_explain` metadata so agents and frontend clients do not need private ranking logic
- the actionability slice is now complete under `0067`:
  - corpus result rows include stable `action_target` metadata for message and derived-text hits
  - API, MCP, and CLI JSON surfaces expose the same shared selection metadata without endpoint-specific mapping
  - later export/report/action workflows can consume selected candidates without re-parsing labels, snippets, or score fields
- the scale and inference-boundary review slice is now complete under `0068`:
  - `search scale-review` reports corpus size, embedding coverage, repeated query latency by retrieval profile, and a machine-readable architecture recommendation
  - the managed `default` baseline review on 2026-04-20 measured `91,556` messages, complete `local-hash-128` coverage, no derived-text chunks, and `p95=2161 ms` for repeated baseline hybrid corpus search
  - the current recommendation is to evaluate a SQLite-native vector extension before any vector DB, while keeping the lightweight baseline inference path in process
- the release/default policy slice is now complete under `0069`:
  - `baseline` remains the installed release-safe default
  - `local-bge` is supported as an explicit operator-controlled local semantic rollout profile
  - `local-bge-rerank` remains experimental
  - DuckDB is sidelined for the first MCP-capable release path and may be revisited later as an analytics/reporting/search sidecar
  - SQLite remains the canonical store; SQLite-native vector extension evaluation is the next search-performance follow-up if latency remains above target
- the MCP retrieval-profile search slice is now complete under `0074`:
  - API and MCP corpus search accept `retrieval_profile`
  - shared app service resolution applies the selected profile's provider/model/weights/rerank settings
  - invalid profile names return structured MCP errors rather than silently falling back
- the managed `default` backlog-drain slice is now complete under `0075`:
  - baseline readiness is now complete for `91,572/91,572` messages and `11,142/11,142` derived-text chunks
  - no derived-text jobs remain pending or errored; remaining extraction warnings are classified skips such as unsupported media or no OCR text
  - no-dataset MCP `search.health` passes with warnings, while derived-text and corpus benchmark checks still fail on local-hash ranking quality and latency
- the managed local-BGE rehearsal slice is now complete under `0076`:
  - managed `user-env install/update --extra local-semantic` now makes optional semantic dependencies reproducible without changing the lightweight default install
  - `local-bge` and `local-bge-rerank` are CUDA-available in the managed runtime
  - `default` has a bounded partial BGE rollout of `500` messages and `500` derived-text chunks
  - full-corpus profile timing remains too slow (`~42.5s` baseline and `~49.0s` partial BGE for the measured query), so broad rollout should wait for search-performance/index and long-lived inference work
- the semantic query performance slice is now complete under `0077`:
  - message semantic candidate retrieval now honors the existing bounded candidate cap
  - derived-text semantic chunk candidates no longer project duplicated full document bodies during chunk search
  - managed `default` baseline scale-review improved from roughly `42-44s` to `p95=396.445 ms` for the measured query
  - partial `local-bge` now has a fast warm run but still pays cold model-load latency, so the next blocking issue is long-lived local inference lifecycle rather than baseline SQLite exact-scan latency
- the local inference service boundary slice is now complete under `0078`:
  - `search inference-serve` starts a loopback-only HTTP service for embedding and rerank requests
  - `search inference-probe` verifies health plus optional embedding/rerank smoke checks
  - HTTP-backed embedding and reranker providers can target the same warm local service
  - managed `user-env` writes and reports a `slack-mirror-inference` wrapper and `slack-mirror-inference.service` unit without making `baseline` dependent on active ML services
- the HTTP-backed BGE profile rehearsal slice is now complete under `0079`:
  - explicit `local-bge-http` and `local-bge-http-rerank` profiles now target the loopback inference service
  - warm managed BGE embedding smoke improved from `14167.488 ms` cold to `119.363 ms` warm
  - warm managed CrossEncoder reranker smoke improved from `6800.081 ms` cold to `133.59 ms` warm
  - managed `default` scale review measured `local-bge-http` p95 `505.873 ms` versus `baseline` p95 `878.193 ms` for the bounded query, with BGE still only partially rolled out
- the live relevance benchmark-lock slice is now complete under `0080`:
  - `search profile-benchmark` compares named retrieval profiles against a JSONL benchmark with aggregate-only output by default
  - managed `default` fixture evidence showed `baseline` and `local-bge-http` tying on low relevance: hit@3 `0.0`, hit@10 `0.666667`, nDCG@k `0.197161`, MRR@k `0.116667`
  - `local-bge-http-rerank` was worse on the same fixture: hit@10 `0.333333`, nDCG@k `0.143559`, MRR@k `0.083333`
  - the existing real-query fixture remains a regression smoke check, not a promotion gate, because relevance remains low and BGE coverage is still partial
- the non-content relevance benchmark-pack slice is now complete under `0081`:
  - `search benchmark-validate` reports dataset label resolvability and configured-model coverage by retrieval profile
  - a nine-query no-body live fixture now exists at `docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl`
  - managed validation resolved `19/19` labels, with `baseline` coverage `19/19` and BGE profile coverage `0/19`
  - profile benchmark evidence remains rollout-limited: `baseline` and `local-bge-http` tied at hit@10 `0.333333`, nDCG@k `0.0789`, while `local-bge-http-rerank` was worse at hit@10 `0.222222`, nDCG@k `0.061032`
- the benchmark-target BGE backfill slice is now complete under `0082`:
  - `mirror benchmark-embeddings-backfill` embeds only targets referenced by benchmark labels for a selected retrieval profile
  - managed target backfill covered `3` unique message targets and moved BGE profile coverage from `0/19` to `19/19` on the non-content fixture
  - post-coverage profile evidence still showed `baseline` and `local-bge-http` tied at hit@10 `0.333333`, nDCG@k `0.0789`; `local-bge-http-rerank` remained worse at hit@10 `0.222222`, nDCG@k `0.061032`
  - the release `baseline` remains unchanged
- the profile-aware benchmark diagnostic slice is now complete under `0084`:
  - `search benchmark-diagnose` reports expected target ranks, top result labels, rank movement, source counts, and compact explain metadata without emitting Slack message bodies by default
  - installed-wrapper evidence showed `baseline` and `local-bge-http` both hitting `4/19` target labels in the top 10 with identical ranks, while `local-bge-http-rerank` demoted two visible hits
  - the next active semantic-search step should be diagnostics-first query formulation or fusion experiments over the same fixture before any broader rollout
- the benchmark-fusion experiment slice is now complete under `0085`:
  - `search health`, `search profile-benchmark`, and `search benchmark-diagnose` now accept explicit corpus `--fusion weighted|rrf`
  - corpus profile benchmarks now honor retrieval-profile weights as well as model/provider/rerank settings
  - installed evidence showed RRF does not help this fixture: `local-bge-http` drops from hit@10 `0.333333` under weighted fusion to `0.0` under RRF
  - `weighted` remains the release default and the next active semantic-search step should focus on query formulation or candidate-generation experiments
- the benchmark-query-variants slice is now complete under `0086`:
  - `search benchmark-query-variants` compares deterministic query rewrites and future authored dataset variants against benchmark fixtures
  - installed evidence showed lowercase ties original, `alnum` slightly lowers rank quality, and `dehyphen` is worse on the current non-content fixture
  - no query-normalization promotion is justified; the next relevance step should target candidate generation or query grammar/operator semantics
- the portable query date-operator slice is now complete under `0087`:
  - message search accepts numeric Slack timestamps plus UTC ISO dates/datetimes for explicit temporal filters
  - `since:`, `until:`, and `on:` now provide portable temporal grammar
  - `participant:` and `user:` now act as Slack sender aliases
  - corpus search suppresses derived-text hits when message-lane operators are present, preventing attachment/OCR rows from bypassing timestamp, sender, or channel constraints
  - shared-parser extraction remains deferred until another communications repo proves compatible behavior
- the LitScout-informed attachment/file query-operator slice is now complete under `0088`:
  - `../litscout` proves the useful pattern is prefix extraction into structured filters plus prefix-pruned service-ready text, not a large copied parser
  - Slack Mirror now has a small lane-aware query helper for derived-text operators such as `has:attachment`, `filename:`, `mime:`, `extension:`/`ext:`, and `attachment-type:`
  - corpus routing now distinguishes message-lane operators from file/attachment-lane operators so `has:attachment` searches derived text instead of suppressing it
  - mixed message-lane plus attachment-lane filters intentionally return no inferred cross-lane join rows until a future schema slice adds explicit message-to-file linkage
- the explicit message-to-file linkage slice is now complete under `0089`:
  - persist `message.files[]` as first-class message/file edges
  - let message search apply `has:attachment`, `filename:`, `mime:`, `extension:`/`ext:`, and `attachment-type:` against linked file metadata
  - allow mixed message-lane plus attachment/file-lane corpus filters to return message rows when the link table satisfies both sides
- the selected-result context-pack slice is now complete under `0090`:
  - selected message `action_target` values can be expanded into bounded before/hit/after message context
  - selected derived-text `action_target` values can be expanded into bounded chunk context and linked Slack messages when backed by attached files
  - CLI, API, and MCP now expose the same context-pack contract as the next handoff layer before selected-result export/report rendering
- the selected-result export artifact slice is now complete under `0091`:
  - selected `action_target` values can now be persisted as managed `selected-results` bundles through CLI, API, and MCP
  - the bundle's neutral `selected-results.json` artifact preserves the generated context pack for later report rendering, action review, or agent handoff
  - the export manifest describes selected-result counts without requiring channel/day metadata
- the selected-result report-viewer slice is now complete under `0092`:
  - managed selected-result bundles now render a human-readable `index.html` report instead of only linking to raw JSON
  - the report shows selected item state, target metadata, message context, derived-text chunk context, and linked Slack messages when present
  - no-text exports render structure while explicitly marking omitted text
- the browser selected-result report-creation slice is now complete under `0093`:
  - authenticated `/search` result cards can select and unselect hits with stable `action_target` metadata
  - the in-page selection tray shows selected count, clears selections, controls context-window/text settings, and posts `kind=selected-results` to the protected export API
  - successful browser-created reports link directly to the managed `/exports/{export_id}` report
- the browser selected-result bulk-affordances slice is now complete under `0094`:
  - authenticated `/search` can select all visible selectable results and deselect only visible selected results
  - the workflow remains browser-local and avoids cross-page saved selection state until the future shared frontend stack exists
- the selected-result report-polish slice is now complete under `0095`:
  - generated selected-result reports now include a sticky summary/action header, item-level copy actions, stable anchors, collapsible context, and print/save-to-PDF styling
  - the neutral `selected-results.json` schema and API/MCP contracts remain unchanged
- `0083` adds a cross-corpus convergence planning layer on top of the shipped
  `action_target` contract: Slack Mirror should evolve selected search results
  toward provider-neutral export/report action targets that can later align
  with `../imcli` chat exports and `../ragmail` thread/report artifacts
- `v0.2.0` is now cut under `P11`, so this lane is no longer blocked on the
  first stable MCP release; the next active semantic slice should resume from
  the existing benchmark/relevance evidence rather than reopening release
  hardening
- the source-label candidate-generation slice is complete under `0135`:
  - plain source-oriented queries can now use a bounded fallback that matches
    mirrored channel ids/names as candidate-generation evidence
  - managed baseline benchmark evidence improved hit@10 from `0.333333` to
    `0.555556` and hit@3 from `0.0` to `0.111111` without a latency regression
  - remaining misses are mainly paraphrase and broader candidate-generation
    failures, so this is an incremental improvement rather than a full
    relevance fix
- the domain-alias candidate-generation slice is complete under `0136`:
  - baseline hit@10 improved from `0.555556` to `0.777778`
  - baseline hit@3 improved from `0.111111` to `0.222222`
  - p95 latency was `477.057 ms`, above the source-label-only run but below
    the benchmark latency failure threshold
  - remaining misses now point more toward source-prior/ranking behavior than
    another broad alias-expansion pass
- the project-language ranking-priors slice is complete under `0137`:
  - narrow project/formulation aliases are now available for lexical candidate
    generation
  - non-generic source-label hits now count as stronger ranking evidence
  - an initial soft-source-term experiment was rejected before commit because
    it regressed hit@3 and latency
  - managed baseline nDCG@k improved from `0.222312` to `0.253767`, while
    hit@10 and hit@3 held at `0.777778` and `0.222222`
  - remaining misses should be handled through grouping/source-prior review
    rather than another small alias expansion
- the corpus source-diversity ordering slice is complete under `0138`:
  - corpus search now interleaves repeated-source rows after scoring without
    dropping rows or mutating score metadata
  - managed baseline hit@10 improved from `0.777778` to `0.888889`
  - managed baseline nDCG@k improved from `0.253767` to `0.286554`, MRR@k
    improved from `0.214815` to `0.244444`, and p95 latency improved to
    `438.661 ms`
  - hit@3 remains `0.222222`, so remaining quality work should focus on
    target-specific semantic retrieval or explicit grouped result presentation
- the benchmark row-level metrics slice is complete under `0139`:
  - aggregate corpus benchmark metrics now score result rows rather than
    flattened label alternatives, aligning `profile-benchmark` with
    `benchmark-diagnose` row-rank semantics
  - managed baseline evidence after the correction is hit@3 `0.666667`,
    hit@10 `1.0`, nDCG@k `0.526822`, MRR@k `0.504762`, and p95 latency
    `435.95 ms`
  - the remaining managed baseline benchmark failure is low nDCG@k, so the
    next relevance work should focus on rank quality rather than treating
    hit@3/hit@10 as the primary blockers
- the lexical coverage rank-quality slice is complete under `0140`:
  - baseline lexical ranking now caps repeated exact hits per query term and
    adds distinct query-concept coverage evidence
  - managed baseline benchmark status improved to `pass_with_warnings`, with
    no failure codes, hit@3 `0.666667`, hit@10 `1.0`, nDCG@k `0.602684`,
    MRR@k `0.60119`, and p95 latency `487.751 ms`
  - BGE and learned rerank still are not promoted; pre-slice comparison showed
    `local-bge-http` effectively tied with baseline and
    `local-bge-http-rerank` lower quality plus slower
- the benchmark target-evidence diagnostic slice is complete under `0141`:
  - `benchmark-diagnose` expected targets now include non-content evidence for
    exact query-term coverage, source-label coverage, missing terms, and target
    resolution counts
  - residual degraded queries now show expected targets often lack one or more
    query terms, supporting fixture/context review or richer semantic-query
    work instead of another immediate baseline ranker tweak

Remaining project phases:
1. live relevance rehearsal and benchmark lock:
   - compare baseline, `bge-m3`, heuristic rerank, and learned rerank against real tenant queries
   - promote high-signal cases into durable benchmark fixtures
2. rollout controls and operator UX:
   - add resumable backfill orchestration and richer operator guidance beyond the shipped read-only readiness and rollout-plan surfaces
3. query pipeline hardening:
   - stabilize grouped result projection now that weighted/RRF fusion and explain metadata are available
4. actionability and frontend integration:
   - browser-side selected-result report creation is now shipped on top of the
     `selected-results.json` artifact and HTML report viewer
   - visible-result bulk selection and report polish are now shipped without
     bloating the temporary Python-rendered UI
   - keep the first implementation Slack-owned, but shape the JSON/report
     artifact so it can become a proving input for a future shared
     communications export contract
5. scale and inference-boundary review:
   - baseline exact search is now interactive for the measured `default` query after `0077`
   - `0078` has landed the long-lived loopback inference-service boundary needed to remove BGE cold-load cost from CLI/API/MCP client processes
6. release/default policy:
   - completed under `0069`

Recommended remaining child plans:
- next semantic child plan should focus on candidate-generation and retrieval-quality diagnostics over the covered benchmark fixture, because profile-aware diagnostics, fusion experiments, and query variants have already shown that ranking-only changes are not enough
- the next export/report actionability child plan should only add new report/export behavior if it closes a concrete release gap; otherwise shift back to relevance diagnostics or the shared frontend architecture track

Planned outputs:
- bounded child plans under `docs/dev/plans/`, following the remaining project phases above
- a local-first retrieval profile that improves message, attachment, and OCR search quality without forcing a vector-DB migration

## P12 | Communications Corpus Convergence

Status: OPEN

Purpose:
- guide Slack Mirror toward convergence with `../imcli` and `../ragmail` through
  shared search/export/report contracts instead of a premature mega-merge
- preserve Slack-specific runtime ownership while making the export/report layer
  portable enough to seed future shared libraries
- align portable query semantics and selected-result action targets before
  treating report/export convergence as complete

Actionable plans:
- `docs/dev/plans/0083-2026-04-21-cross-corpus-export-convergence.md`
- `docs/dev/plans/0121-2026-04-21-slack-report-convergence-design-note.md`
- `docs/dev/plans/0122-2026-04-25-receipts-child-service-profile-homework.md`
- `docs/dev/plans/0123-2026-04-25-receipts-display-label-handoff.md`
- `docs/dev/plans/0124-2026-04-25-receipts-context-window-handoff.md`
- `docs/dev/plans/0125-2026-04-26-receipts-guest-grant-assertion-handoff.md`
- `docs/dev/plans/0126-2026-04-26-receipts-event-emission-handoff.md`
- `docs/dev/plans/0127-2026-04-27-receipts-live-view-readiness.md`
- `docs/dev/plans/0142-2026-04-29-receipts-guest-grants-service-profile.md`
- `docs/dev/plans/0143-2026-04-30-guest-safe-mention-rendering.md`
- `docs/dev/plans/0144-2026-05-01-receipts-compatibility-smoke-gate.md`
- `docs/dev/plans/0145-2026-05-01-receipts-service-profile-contract.md`
- `docs/dev/plans/0146-2026-05-01-receipts-identity-display-fixtures.md`
- `docs/dev/plans/0147-2026-05-01-receipts-event-readiness-lifecycle.md`
- `docs/dev/plans/0148-2026-05-01-receipts-tenant-maintenance-capabilities.md`

Current state:
- Slack Mirror already has the strongest export/report baseline among the
  sibling communication projects:
  - deterministic managed export IDs
  - managed export bundles and manifests
  - stable `/exports/<export-id>` URLs
  - attachment download and preview URLs
  - channel/day JSON as a canonical artifact
  - HTML chat-style rendering
  - DOCX/PDF renderers layered on JSON
  - API export lifecycle routes
  - browser search and export-management surfaces
  - `action_target` metadata on corpus search results
- `../imcli` is planning selected-result chat exports for Google Messages and
  WhatsApp with configurable before/after context windows, managed report
  artifacts, hideable technical IDs, account-owner labels, attachment links,
  and a parseable portable query/action-target contract
- `../ragmail` has analogous mail search, thread rendering, attachment
  extraction, case bundles, and report manifests, but must preserve mailbox,
  folder, MIME, archive/live-source, and email-thread semantics
- `../imcli`'s report convergence note now sharpens the shared target from
  chat-message reports to provider-neutral communication-event reports with
  durable action targets, context expansion, participant roles, attachment
  provenance, hideable technical IDs, owner identity, and room for reactions,
  edits, tombstones, system events, and email-specific evidence
- the maintainable direction is independent provider services plus shared
  contracts and extracted libraries after at least two repos prove compatible
  artifacts
- `../receipts` now needs a machine-readable child-service profile/capability
  response so its shared frontend can discover Slack auth, search,
  selected-result export lifecycle, artifact, and query-operator support
  instead of hardcoding Slack Mirror behavior in the parent
- Slack Mirror now exposes `GET /v1/service-profile` with a machine-readable
  child-service profile for Receipts, including auth/session mode, search and
  evidence routes, selected-result export lifecycle flags, artifact route
  templates, query operators, source metadata hints, and UI affordance flags
- Slack Mirror corpus search now emits `user_label`, `user_name`, and
  `user_display_name` from stored Slack user profile rows, allowing Receipts to
  render human-readable sender names while preserving native `user_id`
  provenance
- Slack Mirror now exposes `GET /v1/context-window` for selected Slack message
  `action_target.id` values, returning Receipts-compatible cursor-backed
  channel or thread streams with human sender/channel labels and native Slack
  provenance preserved under machine-readable fields
- Receipts now forwards a constrained guest-grant assertion when a guest opens
  a granted child report artifact through the parent BFF. Slack Mirror now
  consumes those headers on export/artifact read routes, supports optional HMAC
  verification through a shared secret, and keeps native Slack export storage,
  auth/session behavior, and workspace authorization child-owned.
- Receipts now consumes imcli committed product events through a cursor-backed
  child API and stores only opaque last-read cursor bookmarks parent-side.
  Slack Mirror now exposes `GET /v1/events` as a comparable Slack-owned
  cursor-read surface over committed product events, starting with message,
  thread-reply, file-link, and export-created events; follow/SSE streaming is
  intentionally not advertised yet.
- Receipts Live View gates child readiness on cursor reads, event descriptors,
  and event status. Slack Mirror now satisfies the source-side readiness
  contract under `0127` with descriptor metadata, `GET /v1/events/status`,
  child-owned watermarks, and snake_case event row aliases while keeping
  `eventFollow: false` until a streaming/follow route exists.
- Receipts now has a Slack-only diagnostic lane that calls `GET /v1/events`
  when the Live View source filter is explicitly Slack. The 2026-04-27
  `NOT_FOUND` runtime gap for `/v1/events` was caused by a stale managed API
  install and was addressed by refreshing the user-scoped editable install and
  restarting `slack-mirror-api.service`.
- the Receipts guest-grant route-policy handoff is complete under `0142`:
  - `/v1/service-profile` now exposes a concrete `guestGrants` object with
    guest-safe export/report artifact read routes, local-only mutation/search
    routes, accepted signature modes, and recognized permissions
  - the managed API service has been refreshed/restarted and now serves the
    policy object at `http://127.0.0.1:8787/v1/service-profile`
- Receipts guest previews now have a Slack-owned path to avoid generic mention
  fallbacks: message corpus rows expose guest-safe `matched_text`, selected-result
  context/event text, and context-window text use locally resolved Slack display
  labels plus common Unicode emoji aliases; changed rows retain raw Slack text
  for child-owned provenance/debugging.
- H1, H2, and H4 from the current Receipts homework are complete:
  - H1 added the Slack-owned compatibility smoke gate.
  - H2 hardened `/v1/service-profile` as the stable contract authority with
    explicit UI ownership metadata.
  - H4 pinned guest-facing identity/display fixtures across search,
    context-window, selected-result artifacts, and event projections.
- H3 event readiness/lifecycle expansion is complete: Slack-owned event status
  now exposes oldest/latest cursor metadata, stale-cursor recovery, family
  counts, clearer empty/filter states, and export rename/delete lifecycle events
  so Receipts Live View does not need to scrape logs.
- H5 tenant-maintenance capability expansion is complete: `/v1/service-profile`
  now advertises Slack-owned tenant route/action metadata, `/v1/tenants` now
  includes redacted per-tenant `maintenance_actions`, and
  `/v1/tenants/{tenant}` returns a focused status payload so Receipts settings
  pages do not need to scrape Slack-native HTML or infer action safety.

Shared-library gate:
- do not extract shared libraries yet as speculative architecture
- begin shared library development only after at least two repos can emit or
  losslessly map to compatible provider-neutral artifacts for the same workflow
- the first likely gate is selected-result export/reporting across
  `slack-export` and `../imcli`, including enough shared query semantics that
  portable filters select comparable records and emit compatible action targets
- use `../ragmail` as the third proving implementation before broader
  frontend or control-plane commitments

Recommended shared-library home:
- not inside `slack-export`
- not inside `../imcli`
- not inside `../ragmail`
- create a separate sibling repo when the first extraction gate is met:
  - preferred: `../comm-corpus`
  - acceptable alternative: `../communications-core`

Initial shared-library candidates:
1. `comm-search-contracts`
   - query grammar and AST types, operator capability metadata,
     provider-native extension namespace rules, result fields, readiness, and
     action targets; not a shared search engine
2. `comm-export-contracts`
   - action targets, source refs, conversation/thread/message or event refs,
     participant roles, context windows, communication-event report payloads,
     artifacts, manifests, and attachment links
3. `comm-bundle-store`
   - deterministic export IDs, safe bundle paths, manifest listing, rename,
     delete, URL building, and preview URL metadata
4. `comm-report-renderer`
   - provider-neutral communication-event report JSON to HTML rendering, with
     later DOCX/PDF adapters only after the JSON contract proves stable
5. `comm-context-window`
   - storage-agnostic context expansion policy over backend-provided message
     neighbors
6. `comm-workbench-ui`
   - React/Vite operator/search/export components after CLI/API/MCP contracts
     stabilize

Communication-event contract requirement:
- shared report artifacts should model a provider-neutral event timeline rather
  than Slack-only messages or chat-message-only rows
- selected-result export artifacts now include a first Slack-native `events`
  projection for message rows, derived-text chunks, and linked messages while
  retaining the existing `context_pack` for backwards compatibility
- Slack should map workspace, channel/DM/MPIM, thread timestamp, message
  timestamp, user/bot/app, file/canvas/email preview, reaction, edit, delete,
  and system-event evidence into neutral source, conversation, thread,
  participant, event, attachment, and source-ref fields
- Slack-native IDs and URLs should remain under explicit source/native metadata
  instead of being discarded during neutral mapping
- shared naming must leave room for future email fields such as subject,
  `Message-ID`, `In-Reply-To`, `References`, `To`, `Cc`, `Bcc`, `Reply-To`,
  inline images, forwarded-message blocks, mailing-list metadata, calendar
  invites, raw source hashes, and redaction hooks

Deferred post-convergence TODO:
- graph visualization should wait until the `slack-export`, `../imcli`, and
  `../ragmail` convergence work has completed enough to prove shared search,
  action-target, context-window, export, and report contracts
- if still useful after that point, add a graph inspector as a diagnostic layer
  over the shared communications-corpus model, not as a Slack-only primary UI
- likely useful graph modes:
  - selected search hit -> neighboring messages -> participants -> attachments
    -> export/report candidates
  - source/tenant -> conversation/thread -> message -> attachment/derived text
  - semantic readiness -> profile/model coverage -> benchmark failures
- default to a precise 2D relationship inspector first; keep 3D rendering as an
  optional exploratory mode only after the graph data contract is stable

Slack Mirror development recommendations:
- keep Slack runtime and onboarding independent:
  - Socket Mode
  - Slack app manifest generation
  - tenant credential installation
  - file/canvas repair
  - Slack outbound/listener semantics
- add selected-result export inputs on top of the current channel/day export
  baseline
- adapt or document Slack search operators against the shared portable grammar
  where Slack semantics permit it:
  - boolean terms, phrases, grouping, and negation
  - temporal filters
  - actor filters
  - workspace/channel/thread filters
  - attachment/file filters
  - `slack.*` native extension fields
- emit or map to provider-neutral report JSON while preserving Slack-native
  fields under explicit source/native metadata
- document neutral mappings:
  - workspace -> source
  - channel/DM/MPIM -> conversation
  - thread timestamp -> thread
  - Slack message timestamp -> message
  - Slack user -> participant
  - Slack file/canvas/email preview -> attachment or derived source
- keep the existing managed bundle behavior stable while adding the neutral
  artifact layer

Anti-goals:
- no direct merge of `slack-export`, `../imcli`, and `../ragmail` now
- no shared DB schema as the first step
- no shared sync/runtime/auth package as the first step
- no frontend-first shared package before CLI/API/MCP export contracts stabilize
- no `imcli`-owned or Slack-owned shared package that makes the other projects
  second-class consumers

## P11 | Stable MCP-Capable User-Scoped Release

Status: CLOSED

Purpose:
- cut the first stable user-scoped release where install, update, managed services, and MCP access are reliable enough to be treated as the supported product baseline
- make MCP a practical operator interface rather than a thin but fragile adjunct to the CLI and browser

Actionable plans:
- `docs/dev/plans/0052-2026-04-18-stable-mcp-capable-user-scoped-release.md`
- `docs/dev/plans/0070-2026-04-20-release-check-managed-runtime-gate.md`
- `docs/dev/plans/0071-2026-04-20-mcp-operator-usability-guide.md`
- `docs/dev/plans/0072-2026-04-20-live-mcp-client-acceptance.md`
- `docs/dev/plans/0073-2026-04-20-semantic-mcp-smoke-after-client-restart.md`
- `docs/dev/plans/0128-2026-04-28-mcp-hybrid-search-json-safety.md`
- `docs/dev/plans/0129-2026-04-28-mcp-conversation-discovery.md`
- `docs/dev/plans/0130-2026-04-28-mcp-conversation-search-workflow.md`
- `docs/dev/plans/0131-2026-04-28-mcp-release-smoke-pass.md`
- `docs/dev/plans/0132-2026-04-28-release-candidate-version-cut.md`
- `docs/dev/plans/0133-2026-04-28-v0-2-0-tag-and-post-release-dev-bump.md`
- `docs/dev/plans/0134-2026-04-28-post-release-roadmap-realignment.md`

Current state:
- `v0.2.0` is tagged and pushed as the first stable MCP-capable user-scoped release
- `master` is back on the `0.2.1-dev` development line for post-release work
- user-scoped install, update, rollback, managed live services, browser auth, and MCP surfaces all exist
- recent slices fixed several important installer and runtime regressions, including managed-update path resolution, runtime-report snapshot auth regressions, and tenant-status durability after bounded backfill
- `user-env check-live` now verifies the managed MCP wrapper with a real stdio health probe, not just file presence
- `user-env status` and `user-env check-live` now also verify bounded concurrent MCP readiness across multiple simultaneous wrapper launches
- the managed-runtime gate now also treats the runtime-report service/timer units and active timer scheduling as release-significant state
- `user-env recover-live` can now safely refresh managed install artifacts when launcher or unit-file drift is detected, instead of treating those cases as operator-only by default
- a clean-state install rehearsal now passes the intended product contract:
  - fresh `user-env install` seeds the configured dotenv file automatically
  - the install/update bootstrap gate no longer blocks on workspace credentials before the operator has edited config
  - `check-live` remains the stricter post-onboarding gate for credentials and live units
- `release check --require-managed-runtime` now combines repo release discipline with the installed `slack-mirror-user user-env check-live --json` gate, including real MCP stdio and concurrent MCP readiness probes
- the release MCP operator baseline is now documented around runtime checks, workspace status, search/readiness, outbound sends, listener deliveries, supported preflight gates, tracing, and non-goals
- live MCP client acceptance found and fixed a missing user-bus environment fallback so agent clients launched without `XDG_RUNTIME_DIR` or `DBUS_SESSION_BUS_ADDRESS` no longer misreport active systemd user units as inactive
- the installed MCP wrapper now passes the documented baseline for stdio handshake, tool listing, runtime status, live validation, workspace status, search/readiness, listener lifecycle, and an idempotent DM send to Eric
- after MCP client restart, the connected MCP semantic smoke passed for tool visibility, runtime status, semantic readiness, no-dataset search health, and corpus search across semantic, lexical, hybrid/RRF, all-workspace, and heuristic-rerank modes
- semantic smoke confirmed the release `baseline` profile is ready across `default`, `pcg`, and `soylei`; opt-in BGE profiles remain unavailable in the managed environment until optional model dependencies are installed
- semantic smoke also confirmed two follow-up gaps for `P10`: baseline local-hash semantic relevance is weak on conceptual queries, and MCP corpus search does not yet expose retrieval-profile selection for profile-driven dense search
- the Lei banter harvest workflow exposed a release-significant MCP regression where all-workspace hybrid corpus search could return a private `embedding_blob` bytes field and fail JSON serialization; `0128` fixes the derived-text source leak and adds MCP-side defensive bytes omission
- MCP now exposes a read-only `conversations.list` discovery tool under `0129`, giving agents a bounded way to find MPDM, IM, private-channel, or public-channel candidates by workspace, name, and member labels before using search/context/export tools
- MCP now exposes `search.conversation` under `0130`, letting agents discover or select a conversation, run scoped `in:<channel_id>` corpus search, and receive ready-to-use context-pack/export payloads without manual tool-chaining
- the full managed MCP release-smoke pass under `0131` now passes across runtime, workspace, search, conversation, context-pack, semantic-readiness, search-health, and listener lifecycle surfaces; real outbound writes were intentionally skipped and `release check --require-managed-runtime` still warns only because the version is a development version
- the release-candidate version cut under `0132` moves the canonical package version to `0.2.0`; tagging/publishing remains a separate explicit release step after the strict clean managed-runtime gate passes
- `v0.2.0` is tagged and pushed under `0133`; `master` is back on the `0.2.1-dev` development line for post-release work
- post-release roadmap cleanup under `0134` closes this lane and routes active technical follow-up back to `P10` semantic retrieval quality
- this lane is closed; future release hardening should open a narrower
  post-release maintenance plan rather than reopening the first-release lane
