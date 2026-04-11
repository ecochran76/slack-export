# Slack Export Runbook

This file is the dated turn log for planning and execution continuity.

## Turn 1 | 2026-04-09

- Adopted the deterministic planning contract for this repo.
- Established canonical root planning surfaces:
  - `ROADMAP.md`
  - `RUNBOOK.md`
- Established canonical actionable plan location:
  - `docs/dev/plans/`
- Opened deterministic first-wave plan files:
  - `docs/dev/plans/0001-2026-04-09-platform-foundation.md`
  - `docs/dev/plans/0002-2026-04-09-installer-upgrade-path.md`
  - `docs/dev/plans/0003-2026-04-09-api-mcp-boundary.md`
- Preserved older files under `docs/` and `docs/dev/` as legacy context instead of deleting them.
- Active roadmap lane: `P01 | Platform Foundation`
- Active plan: `docs/dev/plans/0001-2026-04-09-platform-foundation.md`
- Handoff note for the next agent:
  - `docs/dev/planning-contract-handoff-2026-04-09.md`
- Validation:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 2 | 2026-04-09

- Reconciled the deterministic planning contract with the repo's actual implementation state.
- Updated `ROADMAP.md` so service surfaces and outbound/listener work are tracked as active lanes instead of future-only ideas.
- Opened `docs/dev/plans/0004-2026-04-09-outbound-listeners-hardening.md` for outbound and listener contract hardening.
- Updated `docs/dev/plans/0001-2026-04-09-platform-foundation.md` and `docs/dev/plans/0003-2026-04-09-api-mcp-boundary.md` so their non-goals and state no longer contradict shipped API, MCP, outbound, and listener capabilities.
- Converted legacy planning entrypoints to explicit redirects:
  - `docs/ROADMAP.md`
  - `docs/dev/RUNBOOK.md`
  - `docs/dev/PLAN.md`
- Active roadmap lanes:
  - `P01 | Platform Foundation`
  - `P02 | Service Surfaces`
  - `P05 | Outbound Messaging And Listeners`
- Active plans:
  - `docs/dev/plans/0001-2026-04-09-platform-foundation.md`
  - `docs/dev/plans/0002-2026-04-09-installer-upgrade-path.md`
  - `docs/dev/plans/0003-2026-04-09-api-mcp-boundary.md`
  - `docs/dev/plans/0004-2026-04-09-outbound-listeners-hardening.md`
- Validation:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 3 | 2026-04-10

- Reviewed code and git history to reconcile the canonical planning docs with what has actually landed on `master`.
- Confirmed shipped platform baseline since the planning-contract migration:
  - shared application-service layer
  - local API server
  - MCP server
  - managed `user-env` install/update/uninstall/status flow
  - managed API launcher and API systemd user service
  - outbound send/reply support with audit rows and idempotency
  - listener registration, delivery inspection, and acknowledgement paths
  - incremental backfill checkpoint and SQLite backlog fixes
- Updated roadmap lane status and current-state notes so active lanes reflect implemented baseline instead of aspirational future-only work.
- Opened `docs/dev/plans/0005-2026-04-10-live-ops-runtime-hardening.md` for `P04 | Live Ops And Runtime Hardening`.
- Updated active plan files with current-state notes so `OPEN` plans say what is shipped and what remains.
- Active roadmap lanes:
  - `P01 | Platform Foundation`
  - `P02 | Service Surfaces`
  - `P04 | Live Ops And Runtime Hardening`
  - `P05 | Outbound Messaging And Listeners`
- Active plans:
  - `docs/dev/plans/0001-2026-04-09-platform-foundation.md`
  - `docs/dev/plans/0002-2026-04-09-installer-upgrade-path.md`
  - `docs/dev/plans/0003-2026-04-09-api-mcp-boundary.md`
  - `docs/dev/plans/0004-2026-04-09-outbound-listeners-hardening.md`
  - `docs/dev/plans/0005-2026-04-10-live-ops-runtime-hardening.md`
- Validation:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 4 | 2026-04-10

- Reviewed the shared product-engineering policy modules in `/home/ecochran76/workspace.local/agent-policies` against this repo's local `AGENTS.md`.
- Tightened the repo-local policy so it now carries the missing shared governance pieces explicitly:
  - roadmap vs runbook role separation
  - plan activation wiring rules
  - `Current State` expectations for `OPEN` plans
  - git dirty-state and reconciliation discipline
  - validation and handoff rules
  - turn-closeout behavior
  - controlled policy-evolution rules
- Kept repo-specific details local instead of copying generic module prose wholesale.
- Confirmed that personal workspace conventions such as `SOUL.md`, `USER.md`, and `MEMORY.md` remain explicitly out of scope for this repo.
- Validation:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 5 | 2026-04-10

- Took `P04 | Live Ops And Runtime Hardening` as the active implementation slice.
- Added `slack-mirror user-env validate-live` as the supported operator validation command for the managed user environment.
- The validator now checks:
  - managed config loadability
  - configured DB presence
  - enabled workspace presence in the DB
  - explicit outbound write-token configuration
  - expected active API/webhooks/daemon units
  - duplicate legacy `events` / `embeddings` topology
- Queue error rows are surfaced as warnings rather than hard failures so the command distinguishes broken topology from recoverable backlog/history.
- Updated the live-ops docs and the `P04` plan to treat the validation command as part of the supported runtime contract.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_cli -v`
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 6 | 2026-04-10

- Tightened `slack-mirror user-env validate-live` so it now emits stable failure and warning classes instead of flat strings.
- Added recovery hints directly to validator output for:
  - config failures
  - DB and workspace-sync failures
  - missing explicit outbound token failures
  - inactive or missing managed units
  - duplicate-topology failures
- Documented the failure classes and first-response recovery flow in the live-ops docs.
- Updated the `P04` plan current-state note to reflect that failure classification and restart/recovery guidance are now part of the supported runtime contract.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_cli -v`
  - `./.venv/bin/python scripts/check_generated_docs.py`
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 7 | 2026-04-10

- Reviewed the install/update gate idea against the actual product contract and found that `user-env install/update` do not provision workspace live units, only the managed runtime and API service.
- Reused the same validator logic for a narrower managed-runtime gate during `user-env install` and `user-env update`.
- The automatic post-install/update validation now checks:
  - config loadability
  - configured DB presence
  - workspace sync into the DB
  - explicit outbound token requirements
  - managed API unit presence and activity
- Kept full `slack-mirror user-env validate-live` as the explicit gate for the workspace `webhooks` and `daemon` units after live-mode installation.
- Updated the user-install and live-mode docs so the distinction between managed-runtime validation and full live validation is explicit.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_cli -v`

## Turn 8 | 2026-04-10

- Tightened full `slack-mirror user-env validate-live` so it now treats live-mirror failure as more than topology drift.
- Full live validation now fails on:
  - event queue error rows
  - embedding queue error rows
  - pending event backlog above the built-in threshold
  - pending embedding backlog above the built-in threshold
- Kept the narrower install/update validation gate less strict so fresh managed-runtime setup still validates before workspace live units are installed.
- Updated the live-ops docs and `P04` plan to describe the new live-failure policy and queue thresholds.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_cli -v`

## Turn 9 | 2026-04-10

- Exposed live runtime validation through the shared service boundary instead of forcing operators and agents to shell out.
- Added a shared `validate_live_runtime()` method in `slack_mirror.service.app`.
- Added API access at `/v1/runtime/live-validation`.
- Added MCP access through the `runtime.live_validation` tool.
- Kept the transport layers thin by reusing the same underlying validation logic and response shape.
- Updated the `P02` plan current-state note so the API/MCP boundary reflects that live health is now queryable through the shared service surface.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_api_server tests.test_mcp_server tests.test_cli -v`

## Turn 10 | 2026-04-10

- Tightened the live-validation transport contract so automation does not need to parse human-readable lines.
- Added a structured live-validation report in the managed-runtime layer with:
  - overall status
  - failure and warning counts
  - unique failure and warning codes
  - per-workspace queue/error counts and issue codes
- Kept the existing human-readable summary lines so operator CLI output stays familiar.
- Reused that same richer shape through the shared app service, API, and MCP surfaces.
- Updated the `P02` plan current-state note to reflect the machine-readable health summary baseline.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_api_server tests.test_mcp_server tests.test_cli -v`

## Turn 11 | 2026-04-10

- Standardized the API and MCP failure contract for service operations instead of letting each transport invent its own ad hoc error shape.
- Added a shared transport-layer error mapper with stable machine-readable fields:
  - `code`
  - `message`
  - `retryable`
  - `details`
- API failures now return that envelope with operation and workspace context.
- MCP failures now return the same envelope in JSON-RPC `error.data`, with a mapped MCP error status instead of collapsing everything into one generic server error.
- Updated the `P02` plan current-state note so the API/MCP boundary reflects the shared error-envelope baseline.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_api_server tests.test_mcp_server tests.test_cli -v`

## Turn 12 | 2026-04-10

- Tightened the outbound write contract at the shared service boundary so API and MCP callers do not need to infer semantics from raw `outbound_actions` rows.
- Outbound send/reply results now expose explicit machine-readable fields for:
  - parsed `options`
  - parsed upstream `response`
  - `idempotent_replay`
  - `retryable`
- Kept the existing audit rows and DB schema, but normalized the returned shape so repeated idempotent calls are visible to transport consumers.
- Verified that idempotent DM sends still avoid a second `conversations.open` call while now also reporting replay semantics directly.
- Updated the `P02` plan current-state note so the API/MCP boundary reflects the explicit outbound-write contract baseline.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_app_service tests.test_api_server tests.test_mcp_server tests.test_cli -v`

## Turn 13 | 2026-04-10

- Added a stable repo doc for the shipped API/MCP transport contract:
  - `docs/API_MCP_CONTRACT.md`
- Documented the current shared success/error semantics for:
  - live runtime validation
  - outbound message sends
  - outbound thread replies
  - the shared machine-readable error envelope
- Linked the contract from `README.md` and `docs/ARCHITECTURE.md` so callers have one canonical reference instead of relying on tests or code inspection.
- Updated the `P02` plan current-state note to reflect that the shipped transport contract is now documented, not just implemented.
- Validation:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 14 | 2026-04-10

- Extended `docs/API_MCP_CONTRACT.md` so `P05` listener behavior is documented at the same level as outbound write behavior.
- Added explicit transport-contract coverage for:
  - listener registration/update semantics
  - event-type and channel filtering behavior
  - delivery row fields
  - delivery status values
  - acknowledgement and failure-recording semantics
- Linked the listener contract back from `README.md` and `docs/ARCHITECTURE.md` so local consumers have one canonical reference for outbound and listener behavior together.
- Updated the `P05` plan current-state note so the outbound/listener lane reflects that the shipped listener transport semantics are now documented, not just implemented.
- Validation:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 15 | 2026-04-10

- Reviewed `P05` for closure readiness by checking the actual listener failure and replay paths instead of only the docs.
- Fixed a correctness gap in the shared service layer:
  - listener unregister no longer silently succeeds on a missing listener ID
  - delivery ack no longer silently succeeds on a missing delivery ID
- Added regression coverage for:
  - listener name upsert behavior
  - failed delivery acknowledgements with error capture and attempt increments
  - missing-ID behavior through service, API, and MCP surfaces
- Updated the `P05` plan current-state note so the remaining scope is now narrow and explicit.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_app_service tests.test_api_server tests.test_mcp_server tests.test_cli -v`

## Turn 16 | 2026-04-10

- Closed `P05 | Outbound Messaging And Listeners`.
- Closure basis:
  - outbound write-token routing, DM resolution, idempotency, and replay semantics are implemented and tested
  - listener registration, filtering, delivery, and acknowledgement semantics are implemented and documented
  - missing-ID failure behavior is now explicit through service, API, and MCP
  - the local queue-delivery listener model is now treated as the intended shipped baseline, not a temporary placeholder
- Deferred from `P05` closure:
  - richer retry/requeue policy for listeners
  - broader automation features beyond the current local consumer model
- Validation:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 17 | 2026-04-10

- Added machine-readable local operator output for the live-runtime checks:
  - `slack-mirror user-env status --json`
  - `slack-mirror user-env validate-live --json`
- Kept the existing human-readable CLI output for operators, but exposed the same status/validation data in JSON for shell automation and unattended checks.
- Updated the live-ops docs and `P04` current-state note to reflect the new CLI-native machine-output path.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_cli -v`

## Turn 18 | 2026-04-10

- Added `slack-mirror user-env check-live` as the one-command operator smoke gate for the managed runtime.
- The new check combines:
  - managed runtime artifact presence for the CLI, API, and MCP launchers
  - API unit-file presence
  - full live validation of config, DB, workspace sync, explicit outbound tokens, expected units, and queue-health thresholds
- Added `--json` support so the combined smoke gate is machine-readable for unattended release and install checks.
- Kept `status` and `validate-live` as narrower primitives instead of overloading either one.
- Updated the live-ops docs and `P04` current-state note so the operator workflow now includes a single pass/fail smoke command.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_cli -v`
  - `./.venv/bin/python scripts/check_generated_docs.py`
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 19 | 2026-04-10

- Added `slack-mirror user-env recover-live` as the bounded recovery command for `P04`.
- Defined the supported safe auto-remediation policy:
  - `systemctl --user daemon-reload`
  - restart the managed API service when its unit exists but is inactive
  - restart the managed workspace live units when their unit files exist but the units are inactive
- Kept the following explicitly operator-only:
  - config or dotenv fixes
  - DB repair or missing workspace sync
  - outbound token fixes
  - duplicate-topology cleanup
  - queue-content repair beyond unit restarts
- Added `--apply` and `--json` so recovery can be previewed or executed through one supported CLI surface.
- Updated the live-ops docs and `P04` current-state note so the restart-only recovery boundary is explicit.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_cli -v`
  - `./.venv/bin/python scripts/check_generated_docs.py`
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 20 | 2026-04-10

- Tightened the `P04` freshness policy so stale mirrored channels are now part of the supported live-health contract instead of being observability-only.
- Full `slack-mirror user-env validate-live` now fails when a workspace has mirrored channels older than the built-in `24h` freshness window.
- The narrower managed-runtime gate used by `user-env install` and `user-env update` keeps stale freshness as a warning, because those flows do not provision workspace live units.
- Added stale-mirror regression coverage in the `user_env` tests and updated the live-ops docs to show the mirror-status command used to inspect freshness directly.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_cli -v`
  - `./.venv/bin/python scripts/check_generated_docs.py`
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 21 | 2026-04-10

- Closed `P04 | Live Ops And Runtime Hardening`.
- Closure basis:
  - supported live topology is explicit in docs and scripts
  - unattended validation is available through `validate-live`, `check-live`, and machine-readable JSON output
  - bounded safe recovery is available through `recover-live`
  - duplicate topology, inactive units, queue errors, queue backlog, and stale mirror freshness are all part of the supported health contract
  - install/update flows run the narrower managed-runtime gate, while full live installs use the stricter live-service gate
- Deferred beyond `P04` closure:
  - richer non-restart remediation
  - tuning or revising the built-in freshness heuristic
  - any broader orchestration beyond the documented single-host user-service model
- Validation:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 22 | 2026-04-10

- Advanced `P01 | Platform Foundation` by turning rollback from a plan-only expectation into a supported installer command.
- Added bounded `slack-mirror user-env rollback` behavior:
  - update now saves the previous managed app snapshot at `~/.local/share/slack-mirror/app.previous`
  - rollback swaps that snapshot back into place
  - rollback refreshes the managed venv, launchers, and API service
  - rollback explicitly preserves config, DB, cache, and other runtime state
- Made the rollback boundary explicit:
  - it is for bad managed code/runtime updates
  - it does not reverse DB schema, queue contents, or other state mutations made by a newer build
- Updated installer docs and the `P01` installer/upgrade plan so the shipped install/update/rollback behavior is aligned with the repo surface.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_cli -v`
  - `./.venv/bin/python scripts/check_generated_docs.py`
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 23 | 2026-04-10

- Advanced `P01 | Platform Foundation` again by turning release discipline into a supported product command.
- Added `slack-mirror release check` as the canonical repo-level release gate for:
  - version consistency between `pyproject.toml` and runtime package metadata
  - generated CLI docs freshness
  - planning-contract audit health
- Added stricter release-cut flags:
  - `--require-clean`
  - `--require-release-version`
- Fixed MCP initialization metadata so the server now advertises the canonical runtime package version instead of a hardcoded string.
- Added release-discipline docs and updated roadmap/plan current-state notes so the repo’s release path is now executable, not just described.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_release tests.test_mcp_server tests.test_cli -v`
  - `./.venv/bin/python scripts/check_generated_docs.py`
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 24 | 2026-04-11

- Fixed the first portability gap in the new release gate:
  - `slack-mirror release check` no longer hardcodes the planning-audit helper to one workstation path
  - the repo now vendors `scripts/audit_planning_contract.py`
  - the gate still allows `SLACK_MIRROR_PLANNING_AUDIT` or a sibling `agent-policies` checkout as overrides
- Fixed the enforcement gap:
  - GitHub Actions now runs `python -m slack_mirror.cli.main release check` directly
  - the workflow no longer relies on tests plus a separate docs check while ignoring the supported release gate
- Hardened release-gate tests so the planning-audit resolution path is exercised explicitly.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_release tests.test_mcp_server tests.test_cli -v`
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `./.venv/bin/python scripts/check_generated_docs.py`
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 25 | 2026-04-11

- Closed the remaining `P01 | Platform Foundation` planning work.
- Added the missing operator-facing release-cut procedure to `docs/dev/RELEASE_DISCIPLINE.md` so the shipped release gate now has an explicit distinction between:
  - normal development and CI usage via `slack-mirror release check`
  - actual cut-candidate usage via `slack-mirror release check --require-clean --require-release-version`
- Closed `0002 | Installer Upgrade Path` because the repo now has a documented install, update, rollback, validation, and release-gate baseline.
- Closed `0001 | Platform Foundation` because the coordinating lane has served its purpose:
  - deterministic planning wiring is in place
  - old `PHASE_*` docs are no longer active sources of truth
  - future work can proceed through narrower child lanes without keeping the coordination plan open artificially
- Updated `ROADMAP.md` so `P01` is now closed and no longer claims unresolved installer/release work that the repo has already shipped.
- Validation:
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
  - `./.venv/bin/python -m slack_mirror.cli.main release check`

## Turn 26 | 2026-04-11

- Closed `P02 | Service Surfaces`.
- Closure basis:
  - the shared application-service boundary is established in `slack_mirror.service.app`
  - API and MCP are both thin transports over that shared service layer
  - live-validation, outbound writes, listener operations, and structured error handling are documented in `docs/API_MCP_CONTRACT.md`
  - targeted regression coverage now protects the service, API, MCP, and CLI integration points for the shipped contract
- Closed `0003 | API MCP Boundary` because the repo no longer needs to treat the baseline service-surface definition as open-ended hardening work.
- Future API, MCP, or skill-surface expansion should now open narrower follow-up plans instead of keeping the base ownership/contract lane open.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_app_service tests.test_api_server tests.test_mcp_server tests.test_cli -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 27 | 2026-04-11

- Opened `P03 | Search And Evaluation` as a real active lane under `0006 | Search Evaluation Modernization`.
- Added the active plan file:
  - `docs/dev/plans/0006-2026-04-11-search-evaluation-modernization.md`
- Reviewed the current Slack mirror search stack against sibling repos:
  - `slack-export` already has SQLite-backed lexical, semantic, and hybrid message retrieval
  - `../imcli` contributes the stronger shared-core model for canonical message search, derived-text search, tenant safety, and lexical-first hybrid reranking
  - `../ragmail` contributes the stronger extraction, OCR, chunking, provider-routing, and evaluation discipline
- Chose the modernization direction explicitly:
  - keep Slack mirror's SQLite-first baseline
  - adopt first-class derived-text ownership similar to `imcli`
  - adopt staged attachment/OCR extraction and stronger eval/diagnostic discipline similar to `ragmail`
  - avoid making a heavy backend such as OpenSearch the first prerequisite for progress
- Updated `ROADMAP.md` so `P03` is now `OPEN` with one bounded active plan instead of remaining a parked lane with only legacy context.
- Validation:
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 28 | 2026-04-11

- Landed the first implementation slice under `0006 | Search Evaluation Modernization`.
- Added first-class shared-core derived-text storage:
  - `derived_text`
  - `derived_text_fts`
  - `derived_text_jobs`
- Added the first document-native extraction path:
  - canvas HTML extraction
  - UTF-8 text-like file extraction
  - machine-readable PDF extraction when `pdftotext` is available
- Added operator surfaces:
  - `slack-mirror mirror process-derived-text-jobs`
  - `slack-mirror search derived-text`
- Wrote the ownership contract in `docs/dev/DERIVED_TEXT_CONTRACT.md` so `attachment_text` and `ocr_text` semantics are explicit before OCR and broader hybrid retrieval expand further.
- Kept OCR as a modeled but still-open path rather than pretending the first slice solved image-derived extraction.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_db tests.test_search tests.test_derived_text tests.test_cli -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 29 | 2026-04-11

- Landed the second `P03` extraction slice so `ocr_text` is no longer only a modeled placeholder.
- Added OCR job enqueueing for OCR-eligible files:
  - image-like files
  - PDFs
- Added real `ocr_text` extraction through the shared worker:
  - `tesseract_image` for image-like files
  - `tesseract_pdf` for scanned/image-heavy PDFs via `pdftoppm` plus `tesseract`
- Kept the distinction between `attachment_text` and `ocr_text` explicit:
  - PDFs with a text layer remain `attachment_text`
  - their `ocr_text` jobs are skipped as `pdf_has_text_layer`
- Updated the derived-text contract and `P03` plan so OCR is now a shipped partial capability rather than future-only scope.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_db tests.test_derived_text tests.test_search tests.test_cli -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 30 | 2026-04-11

- Landed the next `P03` retrieval slice so search no longer stops at parallel message-only and derived-text-only surfaces.
- Added `slack_mirror.search.corpus` as the shared-core combined retrieval path over:
  - messages
  - derived attachment text
  - OCR-derived text
- Added `slack-mirror search corpus` as the operator surface for corpus-wide lexical, semantic, and hybrid retrieval.
- Kept the current corpus design lexical-first:
  - message retrieval still reuses the existing message search path
  - derived-text lexical search reuses `derived_text_fts`
  - derived-text semantic scoring currently uses the local embedding baseline on shared-core rows
- Deferred from this slice:
  - chunking for long documents
  - API and MCP transport exposure for corpus search
  - stronger evaluation and search-health checks
- Validation:
  - `./.venv/bin/python -m unittest tests.test_search tests.test_cli -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 31 | 2026-04-11

- Landed the next `P03` transport and readiness slice.
- Added shared service methods for:
  - corpus search over messages plus derived text
  - machine-readable search readiness reporting
- Exposed those through both transports:
  - API:
    - `GET /v1/workspaces/{workspace}/search/corpus`
    - `GET /v1/workspaces/{workspace}/search/readiness`
  - MCP:
    - `search.corpus`
    - `search.readiness`
- Updated the transport contract docs so corpus search and readiness are explicit shared API/MCP commitments rather than CLI-only behavior.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_api_server tests.test_mcp_server tests.test_search tests.test_cli -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 32 | 2026-04-11

- Landed the next `P03` evaluation and search-health slice.
- Refactored the older eval harness into shared search-eval helpers so benchmark logic is no longer script-private.
- Added `slack-corpus` benchmark mode to `scripts/eval_search.py` for message-plus-derived-text evaluation.
- Added a shared search-health gate over:
  - readiness counters
  - optional benchmark execution
  - bounded quality and latency thresholds
- Exposed search health through:
  - CLI: `search health`
  - API: `GET /v1/workspaces/{workspace}/search/health`
  - MCP: `search.health`
- Added a corpus smoke benchmark pack and updated the eval docs so the new path is usable.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_app_service tests.test_api_server tests.test_mcp_server tests.test_search tests.test_cli -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 33 | 2026-04-11

- Landed the next `P03` retrieval-depth slice.
- Added shared-core chunk storage for long derived text:
  - `derived_text_chunks`
  - `derived_text_chunks_fts`
- Kept `derived_text` as the canonical non-message document row and treated chunk rows as retrieval-serving children rather than a second document identity.
- Updated derived-text lexical and semantic retrieval so:
  - long attachment and OCR rows are matched through chunk-level search
  - results still roll up to one owning derived-text row
  - best-match snippet metadata now surfaces through:
    - `matched_text`
    - `chunk_index`
    - `start_offset`
    - `end_offset`
- Updated corpus search so long-document results expose chunk-aware snippet text instead of only whole-document snippets.
- Added a deeper corpus benchmark pack beside the smoke fixture for long-document and OCR regression checks.
- Validation:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `./.venv/bin/python scripts/check_generated_docs.py`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 34 | 2026-04-11

- Landed the next `P03` scope-expansion slice for cross-workspace retrieval.
- Added explicit cross-workspace corpus search through the shared service boundary instead of leaving "cross-tenant" as roadmap-only language.
- Kept the contract explicit rather than overloading workspace-scoped paths:
  - CLI: `search corpus --all-workspaces`
  - API: `GET /v1/search/corpus`
  - MCP: `search.corpus` with `all_workspaces=true`
- Added stable workspace metadata on corpus-search results:
  - `workspace`
  - `workspace_id`
- Kept workspace-scoped corpus search intact and backward-compatible.
- Validation:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `./.venv/bin/python scripts/check_generated_docs.py`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 35 | 2026-04-11

- Landed the next `P03` evaluation-hardening slice.
- Tightened search-health quality gating beyond the earlier single hit-rate threshold.
- Benchmark-backed search health now checks:
  - `hit_at_3`
  - `hit_at_10`
  - `ndcg_at_k`
  - `latency_ms_p95`
- Added per-query benchmark diagnostics to the shared eval/report path:
  - `query_reports` on benchmark output
  - `degraded_queries` on search-health output
- Kept the stricter quality contract aligned across CLI, API, and MCP surfaces.
- Validation:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `./.venv/bin/python scripts/check_generated_docs.py`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 36 | 2026-04-11

- Landed the next `P03` extraction-coverage slice.
- Added document-native extraction for common OOXML office attachments without adding a heavyweight dependency path:
  - `.docx` via `ooxml_docx`
  - `.pptx` via `ooxml_pptx`
  - `.xlsx` via `ooxml_xlsx`
- Kept those outputs in the existing shared `attachment_text` contract instead of creating file-type-specific side tables.
- This closes one of the biggest remaining non-message corpus gaps for normal Slack attachments while keeping the extractor path host-local and SQLite-first.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_derived_text tests.test_search -v`
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 37 | 2026-04-11

- Closed `P03 | Search And Evaluation`.
- Closure basis:
  - shared-core search now spans canonical messages plus first-class derived text
  - the shipped extractor set covers canvases, UTF-8 text-like files, OOXML office files, machine-readable PDFs, and OCRable image/scanned-PDF content
  - chunk-aware retrieval is landed for long derived-text rows without inventing a second canonical document identity
  - cross-workspace corpus search is exposed through shared service, CLI, API, and MCP
  - search readiness and search health are machine-readable supported contracts, with smoke and depth benchmark packs plus per-query diagnostics
- Deferred from `P03` closure:
  - provider-routed OCR or extraction paths beyond current host-local tools
  - broader extraction coverage beyond the current shipped document set
  - future ranking-model or backend changes beyond the current SQLite-first hybrid baseline
  - deeper benchmark suites beyond the current smoke and depth packs
- Future search work should open narrower follow-up plans instead of keeping `P03` generically open.
- Validation:
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
