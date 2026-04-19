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

## P10 | Semantic Retrieval And Relevance Hardening

Status: OPEN

Purpose:
- upgrade the current basic local semantic-search baseline into a real retrieval stack that better serves messages, attachments, OCR text, and corpus-wide search
- keep the first stable MCP-capable user-scoped release as the immediate priority, then flesh this lane out into bounded follow-on plans

Actionable plans:
- `docs/dev/plans/0053-2026-04-19-semantic-provider-and-model-seam-hardening.md`
- `docs/dev/plans/0054-2026-04-19-local-semantic-retrieval-architecture.md`
- `docs/dev/plans/0055-2026-04-19-bge-m3-message-embeddings.md`
- `docs/dev/plans/0056-2026-04-19-bge-m3-readiness-and-evaluation.md`
- `docs/dev/plans/0057-2026-04-19-bge-m3-bounded-live-rehearsal.md`

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
- the current optional reranking path is heuristic rescoring, not a true learned reranker
- attachment and derived-text retrieval now exist, which raises the value of higher-quality local embeddings and reranking substantially
- the preferred direction for this lane is local-first rather than hosted-first, with the user's RTX 5080-class workstation making stronger local retrieval models practical
- the first stable MCP-capable release work under `P11` is now good enough that this lane has moved from seam hardening into architecture and the first real message-model path
- the live audit on 2026-04-19 shows the current lexical path is serviceable for exact-match retrieval, while semantic and hybrid paraphrase behavior are poor enough that stronger local retrieval is now an active product need
- derived-text retrieval is structurally present, but live coverage is still sparse to absent in current workspaces, which makes architecture-first rollout preferable to jumping straight into a model swap
- the next implementation-critical step is to evaluate and harden the configured `bge-m3` message path on real paraphrase queries, then extend the same architecture into derived-text chunks and reranking in later bounded slices

Planned subphases:
1. provider and model seam hardening:
   - explicit embedding-provider and reranker-provider boundaries instead of treating `model_id` as enough abstraction
2. local retrieval architecture:
   - decide the durable local-first retrieval stack, service boundary, storage/index strategy, and rollout phases before adding heavy models
3. local embedding upgrade:
   - replace or supplement `local-hash-128` with a real local embedding model, likely centered on `bge-m3` or an equivalent local-first alternative
4. chunk and derived-text retrieval upgrade:
   - embed and retrieve over `derived_text` and `derived_text_chunks` as first-class semantic targets, not only messages
5. learned reranking:
   - introduce a real local reranker, likely centered on `bge-reranker-v2-m3` or an equivalent cross-encoder path, over top-K hybrid candidates
6. evaluation and operator diagnostics:
   - add Slack-specific retrieval benchmarks, relevance diagnostics, and live operator visibility for embedding backlog, model health, and rerank coverage
7. MCP and API contract refinement:
   - expose the stronger retrieval options through stable CLI, API, and MCP semantics without breaking the first-release contract

Planned outputs:
- bounded child plans under `docs/dev/plans/`, starting with a retrieval-architecture plan that locks the next implementation direction
- a local-first retrieval profile that improves message, attachment, and OCR search quality without forcing a vector-DB migration

## P11 | Stable MCP-Capable User-Scoped Release

Status: OPEN

Purpose:
- cut the first stable user-scoped release where install, update, managed services, and MCP access are reliable enough to be treated as the supported product baseline
- make MCP a practical operator interface rather than a thin but fragile adjunct to the CLI and browser

Actionable plans:
- `docs/dev/plans/0052-2026-04-18-stable-mcp-capable-user-scoped-release.md`

Current state:
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
- the repo still lacks one explicit release-hardening lane that treats install/update reliability, managed-service health, and MCP usability as one coordinated product target
- MCP is present and functional, but it has not yet been hardened and validated as a release-quality interface with clear readiness criteria, predictable failure handling, and explicit operator guidance
- this lane is the immediate priority before `P10`; semantic retrieval improvements remain planned follow-on work after this release target is reached

Planned subprojects:
1. installer and updater reliability:
   - `user-env install`, `user-env update`, and rollback behavior
   - managed app snapshot correctness
   - release-safe upgrade and repair paths
2. managed service health:
   - API, daemon, webhook/socket-mode, and runtime-report service stability after install, restart, and update
   - operator-visible health gates and bounded recovery paths
3. MCP contract usability:
   - clarify supported MCP tool coverage
   - harden machine-readable success and error behavior
   - reduce surprising preconditions and weak operator feedback
4. release validation and smoke coverage:
   - define the release gate for a user-scoped install
   - ensure `check-live` and related status paths are trustworthy as release criteria
5. operator documentation and runbook fit:
   - tighten the docs for install, update, health checking, and MCP usage so the supported path is obvious

Definition of done for this lane:
- a clean user-scoped install can reach a healthy managed state using the documented path
- update and restart flows are repeatable and recoverable
- MCP is documented and validated as a reliable supported interface for the shipped baseline
- release-readiness can be checked by explicit repo-owned validation commands rather than chat memory or manual guesswork
