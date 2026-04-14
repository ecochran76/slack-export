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

## Turn 17 | 2026-04-13

- Opened and closed `docs/dev/plans/0014-2026-04-13-frontend-auth-bootstrap-provisioning.md` as a narrow `P02` child slice.
- Added `slack-mirror user-env provision-frontend-user` as the supported first-user bootstrap path for local browser auth.
- Kept the CLI thin over the shared frontend-auth service seam:
  - new operator path provisions a local auth user without reopening browser self-registration
  - prompted password entry is the default path
  - unattended bootstrap is supported through `--password-env`
  - existing local users can be rotated explicitly through `--reset-password`
- Updated the auth/config docs so closed self-registration now points operators at the bootstrap command instead of implying temporary policy reversal.
- Validation:
  - `python -m py_compile slack_mirror/core/db.py slack_mirror/service/frontend_auth.py slack_mirror/service/app.py slack_mirror/service/user_env.py slack_mirror/cli/main.py tests/test_frontend_auth.py tests/test_user_env.py tests/test_cli.py`
  - `./.venv/bin/python -m unittest tests.test_frontend_auth tests.test_user_env tests.test_cli -v`
  - `./.venv/bin/python -m slack_mirror.cli.main docs generate --format markdown --output docs/CLI.md`
  - `./.venv/bin/python -m slack_mirror.cli.main docs generate --format man --output docs/slack-mirror.1`
  - `./.venv/bin/python scripts/check_generated_docs.py`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

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

## Turn 38 | 2026-04-11

- Reopened `P03 | Search And Evaluation` only as a narrow follow-up lane after closing the broader modernization baseline.
- Opened `docs/dev/plans/0007-2026-04-11-extraction-provider-expansion.md`.
- Chose provider-routed extraction and OCR as the next bounded slice because the main remaining search gap is extraction depth and coverage visibility, not corpus shape or transport surface.
- Kept the reopened scope narrow and explicit:
  - provider boundary for extraction and OCR
  - richer extraction outcome reporting
  - bounded format expansion under the shared `derived_text` contract
- Kept the previously shipped SQLite-first search baseline closed through `0006` rather than turning `P03` back into a generic catch-all.
- Validation:
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 39 | 2026-04-11

- Landed the first `0007` implementation slice for post-baseline extraction follow-up work.
- Added a shared extraction-provider seam in `slack_mirror.sync.derived_text` instead of keeping job execution hardwired to one local implementation path.
- Kept `LocalCliDerivedTextProvider` as the default implementation so the current host-local OCR and extraction toolchain remains the baseline behavior.
- Started recording provider identity in derived-text metadata so future coverage and outcome reporting can distinguish host-local extraction from later provider-routed paths.
- Added regression coverage proving:
  - `process_derived_text_jobs()` accepts a custom provider
  - provider identity is persisted in derived-text metadata
  - the default local provider path still works
- Validation:
  - `./.venv/bin/python -m unittest tests.test_derived_text -v`
  - `python -m py_compile slack_mirror/sync/derived_text.py tests/test_derived_text.py`

## Turn 40 | 2026-04-11

- Landed the next `0007` reporting slice.
- Expanded `search.readiness` so derived-text readiness now includes, per derivation kind:
  - provider coverage
  - job status buckets
  - machine-readable issue reasons
- Kept that richer reporting on the existing readiness/search-health surfaces instead of adding another parallel status endpoint.
- Updated CLI operator output so non-JSON `search health` also surfaces provider and issue summaries when present.
- Added service-level regression coverage for provider, backlog, skipped-job, and error-reason reporting.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_app_service tests.test_api_server tests.test_mcp_server -v`
  - `python -m py_compile slack_mirror/service/app.py slack_mirror/cli/main.py tests/test_app_service.py`

## Turn 41 | 2026-04-11

- Landed the next `0007` policy slice on top of the new readiness reporting.
- `search.health` now applies explicit extraction-health policy instead of treating extraction visibility as passive counters only.
- Added extraction-health thresholds and codes:
  - failures for derived-text error presence
  - warnings for pending backlog above threshold
  - warnings for non-benign extraction issue reasons
- Kept `pdf_has_text_layer` excluded from OCR issue warnings because it is an expected skip, not an operational defect.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_app_service -v`
  - `python -m py_compile slack_mirror/service/app.py tests/test_app_service.py`

## Turn 42 | 2026-04-11

- Landed the first non-default extraction provider behind the shared provider seam.
- Added `CommandDerivedTextProvider` and config-based provider selection through `search.derived_text.provider`.
- Kept `LocalCliDerivedTextProvider` as the default baseline and made the command-backed path explicitly opt-in.
- Defined the command-provider protocol as JSON-in over stdin and JSON-out over stdout so wrapper processes can integrate without changing shared DB ownership.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_derived_text tests.test_app_service -v`
  - `python -m py_compile slack_mirror/sync/derived_text.py slack_mirror/cli/main.py tests/test_derived_text.py`

## Turn 43 | 2026-04-11

- Expanded local attachment extraction coverage to OpenDocument office files under the existing `attachment_text` contract.
- Added `.odt`, `.odp`, and `.ods` extraction through `content.xml` parsing with `odf_odt`, `odf_odp`, and `odf_ods` extractors.
- Kept the provider and shared-core ownership model unchanged; this is format expansion, not a new storage path.
- Validation:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 44 | 2026-04-11

- Added the first built-in remote extraction transport with `HttpDerivedTextProvider`.
- Kept the provider contract aligned with the command-backed provider by reusing the same JSON request and response schema.
- Added optional bearer-token and header configuration so external extractors can be authenticated without changing shared DB ownership.
- Validation:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 45 | 2026-04-11

- Added default local fallback wrapping for remote derived-text providers so command and HTTP extraction degrade to host-local tooling when remote extraction fails.
- Preserved the actual provider used in metadata and now record `fallback_from` and `fallback_error` when local fallback wins.
- Added config control through `fallback_to_local` so operators can disable fallback when they want strict remote-only behavior.
- Validation:
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 46 | 2026-04-11

- Improved `.docx` searchability by making `ooxml_docx` extraction story-aware across body, headers, footers, footnotes, and endnotes.
- Replaced the old document-body-only XML flattening path with visible-text extraction that preserves tabs and breaks before normalization.
- Kept the extractor name and shared `attachment_text` contract unchanged.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_derived_text -v`
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 47 | 2026-04-11

- Improved `.pptx` and `.xlsx` searchability by replacing generic OOXML XML flattening with visible-text-aware slide parsing and shared-string-aware worksheet parsing.
- `.pptx` now captures slide text runs plus explicit break/tab separators before normalization.
- `.xlsx` now resolves shared strings, inline strings, and direct cell values across worksheet parts.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_derived_text -v`
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 48 | 2026-04-11

- Closed `docs/dev/plans/0007-2026-04-11-extraction-provider-expansion.md` after reviewing the shipped provider and format-expansion baseline against its own acceptance criteria.
- The closure basis is now explicit:
  - shared extraction-provider seam exists
  - host-local extraction remains the default baseline
  - command-backed and HTTP-backed providers are shipped, with local fallback supported by default
  - machine-readable extraction readiness and health reporting are shipped
  - post-baseline format expansion now covers story-aware `.docx`, visible-text-aware `.pptx`, shared-string-aware `.xlsx`, and OpenDocument office files
- Deferred follow-up remains narrow and explicit instead of keeping `P03` broadly open:
  - provider-specialized OCR or extraction
  - stronger extraction policy only if operators need stricter guarantees
  - possible reuse of `docx-skill` OOXML primitives for future export-quality work
- Validation:
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 49 | 2026-04-11

- Reopened `P03` only through a new narrow follow-up plan instead of broadly reopening search modernization.
- Opened `docs/dev/plans/0008-2026-04-11-export-quality-ooxml.md` for export-quality OOXML work.
- Grounded that plan in the repo's actual shipped export surfaces:
  - `scripts/export_channel_day.py`
  - `scripts/export_channel_day_pdf.py`
  - `scripts/export_multi_day_pdf.py`
  - `scripts/export_semantic_daypack.py`
- Scoped the new plan around:
  - export-surface audit
  - bounded `docx-skill` primitive reuse
  - explicit DOCX-quality export contract and QA
- Kept the new work narrow: this is not a reopening of generic search or office-document editing.
- Validation:
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 50 | 2026-04-11

- Completed Track A audit for `docs/dev/plans/0008-2026-04-11-export-quality-ooxml.md`.
- Reviewed the repo's actual export surfaces and confirmed the ownership path:
  - `scripts/export_channel_day.py` is the canonical content assembly step
  - `scripts/export_channel_day_pdf.py` and `scripts/export_multi_day_pdf.py` are renderers over that artifact
  - `scripts/export_semantic_daypack.py` is an orchestrator over the same channel/day export path
- Chose the first DOCX-quality target explicitly: single channel/day export.
- Recorded the architectural rule for the next slice:
  - future DOCX rendering should consume the channel/day JSON export artifact
  - multi-day and semantic daypack DOCX output should compose from that path instead of querying SQLite independently
- Validation:
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 51 | 2026-04-11

- Landed the first implementation slice for `docs/dev/plans/0008-2026-04-11-export-quality-ooxml.md`.
- Added `scripts/export_channel_day_docx.py` as a bounded DOCX renderer over the existing channel/day JSON export artifact.
- Kept the export ownership path explicit:
  - `scripts/export_channel_day.py` remains the canonical content assembly step
  - the DOCX renderer consumes JSON instead of querying SQLite directly
- Current DOCX baseline includes:
  - title and channel/day metadata
  - speaker/timestamp metadata lines
  - thread-reply labeling and indentation
  - clickable attachment links for local files and permalinks
- Added regression coverage in `tests/test_export_docx.py` for OOXML package structure, reply indentation, and hyperlink relationships.
- Updated `docs/dev/EXPORTS.md`, `README.md`, and `ROADMAP.md` to reflect the new renderer.

## Turn 52 | 2026-04-11

- Tightened the initial DOCX renderer around presentation quality without changing the export ownership path.
- Added explicit DOCX paragraph styles for:
  - metadata
  - reply metadata
  - message body
  - reply body
  - attachment items
- Improved attachment presentation so DOCX output now distinguishes:
  - local-only file sources
  - permalink-backed files
- Extended `tests/test_export_docx.py` to lock in the style set and the richer attachment/source semantics.

## Turn 53 | 2026-04-11

- Added bounded multi-day DOCX composition on top of the existing channel/day JSON renderer.
- Added `scripts/export_multi_day_docx.py` as the composition path for multiple channel/day JSON bundles.
- Kept ownership explicit:
  - single-day and multi-day DOCX output both build from the same JSON artifact
  - semantic daypack DOCX output now composes through that same path instead of querying SQLite independently
- Added regression coverage for page-break-based multi-day DOCX composition in `tests/test_export_docx.py`.

## Turn 54 | 2026-04-12

- Added `scripts/validate_export_docx.py` as a bounded structural validator for export DOCX packages.
- The validator reports:
  - required OOXML parts
  - style IDs
  - hyperlink count and targets
  - page-break count
  - reply-badge presence
  - local/permalink attachment note presence
- Added regression coverage in `tests/test_export_docx.py` for both valid DOCX summaries and invalid/missing-part detection.

## Turn 55 | 2026-04-12

- Hardened `scripts/validate_export_docx.py` from a shallow part-check into a bounded OOXML package validator.
- Added package-level checks for:
  - XML parseability across XML and relationship parts
  - `[Content_Types].xml` overrides that point to real package parts
  - internal relationship targets that resolve to real package parts
- Kept the slice narrow:
  - no renderer changes
  - no external runtime dependency on `docx-skill`
  - only selective reuse of its package-validation ideas
- Added regressions in `tests/test_export_docx.py` for:
  - broken internal relationship targets
  - broken content-type overrides
- Validation:
  - `./.venv/bin/python -m unittest tests.test_export_docx -v`
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 56 | 2026-04-12

- Generated real single-day and multi-day DOCX export examples and rendered them through the local `docx-skill` LibreOffice-based QA path instead of relying on XML inspection alone.
- Found and fixed a real compatibility bug in `scripts/export_channel_day_docx.py`:
  - `word/_rels/document.xml.rels` was being emitted with `ns0:`-prefixed relationship elements
  - LibreOffice would not load that package for render/vision QA
  - registering the package relationships namespace as the default output namespace fixed the issue
- Tightened the default DOCX rendering contract around the visual target requested for this lane:
  - 1in margins
  - sans-serif 10pt body text
  - more compact header metadata
  - quieter reply presentation without visible `thread=...` debug data
  - human-readable attachment type labels instead of raw MIME strings
- Confirmed the updated output visually on:
  - a thread-and-attachment-heavy single-day export
  - a bounded two-page multi-day daypack export
- Validation:
  - `./.venv/bin/python -m unittest tests.test_export_docx -v`
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 57 | 2026-04-12

- Added bounded appearance configurability to the DOCX export renderers instead of freezing one hardcoded look:
  - `--font-family`
  - `--font-size-pt`
  - `--margin-in`
  - `--compactness compact|cozy`
  - `--accent-color`
- Kept the contract narrow:
  - no arbitrary theme schema
  - no per-style manual overrides
  - one shared style object for single-day and multi-day DOCX rendering
- Added regression coverage in `tests/test_export_docx.py` for custom font, margin, size, spacing, and accent color output.
- Rendered a configurable sample (`Aptos`, `11pt`, `1.25in`, `cozy`, purple accent) through the local `docx-skill` render path and confirmed it remained visually sane.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_export_docx -v`
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 58 | 2026-04-12

- Added named DOCX visual fixture profiles to the export QA contract instead of relying on one-off manual examples:
  - `compact_default`
  - `cozy_review`
- Added regression coverage in `tests/test_export_docx.py` to lock in the distinct style shape for those fixture profiles:
  - font family
  - body size
  - page margin
  - compact vs cozy indentation/spacing behavior
  - accent color
- Updated the export docs and active `0008` plan so future visual review work has explicit canonical profiles to compare against.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_export_docx -v`
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 59 | 2026-04-12

- Added `scripts/render_export_docx_fixtures.py` as the repo-local one-command path for persisted DOCX export review artifacts.
- The fixture generator now:
  - writes canonical sample channel/day JSON inputs
  - renders single-day and multi-day DOCX outputs for the named fixture profiles
  - records structural validation output in a generated `manifest.json`
  - optionally renders PDF/PNG review artifacts through the local `docx-skill` render path
- This closes the gap between structural DOCX tests and repeatable visual review without making the export lane depend on ad hoc manual commands.
- Added regression coverage in `tests/test_export_docx.py` for:
  - manifest/output generation without external render tools
  - rendered-artifact recording with a mocked render step
- Validation:
  - `./.venv/bin/python -m unittest tests.test_export_docx -v`
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 60 | 2026-04-12

- Refined the DOCX renderer around readability and link safety instead of adding more surface area:
  - added subtle paragraph shading for message and reply blocks
  - reduced the sender/timestamp metadata indent so message ownership reads closer to the content block
  - added portable attachment-type badges to attachment labels instead of relying on brittle emoji glyph fallback
  - stopped treating local mirror filesystem paths as primary hyperlinks
- The renderer now prefers explicit attachment `public_url` / `download_url` fields, then Slack permalinks, and falls back to a labeled local mirror reference when no public URL exists.
- Recorded the longer-term direction in the export docs and active plan:
  - service-configured HTTP/HTTPS attachment URLs behind the live mirror deployment
  - reverse-proxied download endpoints instead of `file://` leakage into Word exports
- Validation:
  - `./.venv/bin/python -m unittest tests.test_export_docx -v`
  - `./.venv/bin/python -m unittest discover -s tests -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 61 | 2026-04-12

- Added config-backed managed export bundling to `scripts/export_channel_day.py` instead of leaving export outputs as ad hoc HTML/JSON files with brittle local attachment references.
- Managed export bundles now:
  - write to a user-scoped `exports.root_dir`
  - use deterministic human-readable export IDs with a short stable hash suffix
  - copy local attachment payloads into the bundle under `attachments/...`
  - emit config-backed local/external download URLs for attachment references
- Added local API static serving for export artifacts under:
  - `/exports/<export-id>/<filepath>`
- Reserved the future preview route explicitly without implementing it yet:
  - `/exports/<export-id>/<filepath>/preview`
- Removed the hardcoded API port mismatch by making `slack-mirror api serve` default to `service.bind` and `service.port` from config.
- Updated the export and config docs to reflect:
  - `http://slack.localhost`
  - `https://slack.ecochran.dyndns.org`
  - the direct download path contract for managed export bundles
- Validation:
  - `./.venv/bin/python -m unittest tests.test_exports tests.test_api_server tests.test_cli -v`

## Turn 62 | 2026-04-12

- Tightened the managed export attachment contract so downstream renderers do not have to guess between local paths and exported URLs.
- `scripts/export_channel_day.py` now emits the same stable exported attachment URL under both:
  - `download_url`
  - `public_url`
- HTML export now prefers `public_url` / `download_url` before falling back to Slack permalinks or local paths.
- PDF renderers now follow the same portable-link preference instead of privileging local filesystem paths.
- This keeps HTML, PDF, and DOCX aligned on one attachment-link contract for managed export bundles.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_export_channel_day tests.test_exports tests.test_api_server tests.test_cli -v`

## Turn 63 | 2026-04-12

- Added bounded in-browser preview support for managed export files through:
  - `/exports/<export-id>/<filepath>/preview`
- Current preview support is intentionally narrow:
  - images render inline
  - PDFs render in an iframe
  - text-like files render as escaped text
  - unsupported binary formats fail explicitly with `PREVIEW_UNSUPPORTED`
- Kept the preview implementation inside the local API instead of introducing a second export-serving surface.
- Updated export/config docs and the active `0008` plan to reflect the shipped preview contract.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_api_server tests.test_export_channel_day tests.test_exports tests.test_cli -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 64 | 2026-04-12

- Extended the bounded export preview path to support `.docx` without introducing a full office-server dependency.
- The local API now uses `mammoth` to render `.docx` previews to HTML under:
  - `/exports/<export-id>/<filepath>/preview`
- Kept the preview contract intentionally lightweight:
  - no edit surface
  - no broad Office-suite runtime
  - no promise of perfect Word fidelity
- Updated dependency, docs, and tests to make `.docx` preview a real repo-level contract rather than a local experiment.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_api_server tests.test_export_channel_day tests.test_exports tests.test_cli -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 65 | 2026-04-12

- Corrected the live-runtime health contract for multi-channel Slack workspaces.
- `user-env validate-live` previously failed on any stale mirrored channel, which produced false positives in workspaces with many legitimately quiet channels.
- Added daemon heartbeat tracking and changed full live validation to fail on missing or stale daemon progress instead of raw stale-channel counts.
- Kept stale-channel counts as warnings and directed operators to `mirror status --classify-access` for gap analysis.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_cli -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 66 | 2026-04-12

- Tightened `mirror status --classify-access` so stale warnings are easier to interpret in real workspaces.
- Fixed the workspace-filter bug in access classification, which previously leaked other workspaces into the report when `--workspace` was set.
- Added percentages, interpretation labels, and sample A-bucket/C-bucket channels to the classification payload and human output.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_status_and_verify -v`

## Turn 67 | 2026-04-12

- Extended `mirror status --classify-access` sample entries with channel class and bounded message-history context.
- A-bucket samples now show channel class plus last-message age, so stale-but-mirrored channels are easier to judge.
- C-bucket samples now carry an explicit `no_messages_recorded` status, which makes never-mirrored shells clearer in machine output.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_status_and_verify -v`

## Turn 68 | 2026-04-12

- Split zero-message access classification into shell-like IM/MPIM channels versus unexpected empty public/private channels.
- Added `C_shell_like` and `C_unexpected_empty` counts plus clearer sample statuses to make the C bucket less ambiguous in live triage.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_status_and_verify -v`

## Turn 69 | 2026-04-12

- Aligned `user-env validate-live` with the richer access-classification evidence.
- `STALE_MIRROR` is now suppressed in full live validation when a workspace has active recent channels and no unexpected empty public/private channels.
- Kept the warning path for real suspicious cases, especially unexpected empty channels without recent activity.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_cli -v`

## Turn 70 | 2026-04-12

- Added plain-text suppression reporting for live validation.
- When stale evidence is intentionally suppressed, `validate-live` now prints an explicit `OK` line with stale count, active recent count, and unexpected-empty count, so operators do not need `--json` to understand why the workspace still passes.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env tests.test_cli -v`

## Turn 71 | 2026-04-12

- Promoted managed export bundles from a script-only artifact to a first-class service object.
- Managed channel/day bundles now write `manifest.json` alongside `channel-day.json` and emit:
  - audience-keyed `download_urls`
  - audience-keyed `preview_urls`
  - selected `download_url` / `preview_url` for the requested default audience
- The local API now exposes export manifests through:
  - `/v1/exports`
  - `/v1/exports/<export-id>`
- Those manifest endpoints rebuild local/external bundle URLs from current config, so the live service owns the HTTP/HTTPS export contract instead of freezing it entirely into one export-time audience choice.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_exports tests.test_export_channel_day tests.test_api_server -v`

## Turn 72 | 2026-04-12

- Extended bounded export preview support to `.pptx` and `.xlsx`.
- `.pptx` preview now renders slide-by-slide HTML summaries from the existing OOXML extraction path.
- `.xlsx` preview now renders bounded sheet-table HTML summaries from the existing OOXML extraction path.
- Kept the preview architecture lightweight and deterministic:
  - no office-server dependency
  - no edit surface
  - no promise of pixel-perfect Office fidelity
- Validation:
  - `./.venv/bin/python -m unittest tests.test_api_server tests.test_derived_text tests.test_exports -v`

## Turn 73 | 2026-04-12

- Extended the same lightweight export preview architecture to the OpenDocument office formats.
- `.odt` preview now renders a bounded text summary.
- `.odp` preview now renders slide-by-slide HTML summaries.
- `.ods` preview now renders bounded sheet-table HTML summaries.
- Kept the contract aligned with the existing office preview stance:
  - no office-server dependency
  - no edit surface
  - deterministic extraction-first rendering
- Validation:
  - `./.venv/bin/python -m unittest tests.test_api_server tests.test_derived_text tests.test_exports -v`

## Turn 74 | 2026-04-12

- Closed `0008 | Export Quality OOXML`.
- Closed `P03 | Search And Evaluation`.
- Closure basis:
  - search modernization, derived-text expansion, and export-quality follow-up are all shipped through bounded plans
  - the export baseline now includes:
    - canonical JSON-first DOCX rendering
    - multi-day/daypack composition
    - structural validation and review fixtures
    - managed export bundles and API-served manifests
    - lightweight preview coverage across PDF, OOXML, and OpenDocument formats
- Future work should open a new narrow plan instead of keeping `P03` open as a catch-all lane.
- Validation:
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 75 | 2026-04-12

- Hardened managed channel/day export localization for hosted Slack attachments.
- If an attachment is present in mirrored message/file metadata but its `files.local_path` is still empty, the exporter now uses the configured workspace token and `url_private_download` to download the binary directly into the export bundle instead of leaving a Slack permalink in the published report.
- Kept the existing fallback for Slack-native `email`/HTML preview attachments that have no binary download path.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_export_channel_day -v`

## Turn 76 | 2026-04-12

- Hardened shared Slack file downloading against bogus HTML success cases.
- `download_with_retries()` now rejects Slack HTML/login interstitial responses instead of treating them as successful binary downloads.
- This fixes the export failure mode where a hosted image could be published as a broken local `.png` that actually contained HTML.
- When the workspace token cannot really fetch the file, exports now fall back honestly to the Slack permalink until credentials or scopes are corrected.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_downloads tests.test_export_channel_day -v`

## Turn 77 | 2026-04-12

- Added a bounded file-repair operator path: `slack-mirror mirror reconcile-files`.
- The command scans mirrored `files` rows that still have `url_private_download` but no usable on-disk file, then attempts bounded repairs into the normal cache layout.
- Kept the repair logic aligned with existing backfill ownership:
  - same token/auth-mode guardrails
  - same cache layout
  - same `update_file_download()` post-download path
- Validation:
  - `./.venv/bin/python -m unittest tests.test_backfill tests.test_cli tests.test_downloads tests.test_export_channel_day -v`

## Turn 78 | 2026-04-12

- Extended `mirror reconcile-files` with structured failure reporting and `--json` output.
- Failure counts are now classified by reason, so bounded repair runs can distinguish cases like:
  - `email_container`
  - `email_container_with_attachments`
  - `html_interstitial`
  - `not_found`
  - `forbidden`
  - `timeout`
- This turns live repair passes into something operators can actually triage instead of a blind `failed=N`.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_backfill tests.test_cli tests.test_downloads tests.test_export_channel_day -v`

## Turn 79 | 2026-04-12

- Added the first real remediation path for Slack-for-Gmail `mode=email` files in `mirror reconcile-files`.
- The repair path now materializes the email body as local HTML instead of trying to binary-download the top-level email container.
- When the preview HTML references inline `files-email-priv` assets that are token-downloadable, those assets are downloaded into a sibling local asset directory and the HTML is rewritten to point at the localized copies.
- Managed export bundle copying now preserves those companion email asset directories, so repaired email artifacts remain self-contained when published under `/exports/<export-id>`.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_backfill tests.test_export_channel_day -v`

## Turn 80 | 2026-04-12

- Tightened `mirror reconcile-files` operator reporting so successful repairs are split into:
  - ordinary binary downloads
  - materialized Slack-for-Gmail email containers
- This keeps the command output honest about what kind of recovery actually happened, especially after the new `mode=email` remediation path landed.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_backfill tests.test_cli tests.test_downloads tests.test_export_channel_day -v`

## Turn 81 | 2026-04-12

- Added warning-side parity for Slack-for-Gmail email-container repair.
- `mirror reconcile-files` now distinguishes:
  - full email-container materialization
  - partial email-container materialization where the HTML body was repaired but one or more inline assets could not be localized
- Partial email repair now surfaces as `email_container_inline_assets_partial` in warning output instead of disappearing into the success bucket or being misreported as a hard failure.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_backfill tests.test_cli tests.test_downloads tests.test_export_channel_day -v`

## Turn 82 | 2026-04-12

- Added remediation hints to `mirror reconcile-files` warning/failure reporting.
- Both plain output and `--json` now include per-reason next-step guidance, so operators do not need to infer what `html_interstitial`, `email_container_with_attachments`, or `email_container_inline_assets_partial` mean from the code.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_backfill tests.test_cli tests.test_downloads tests.test_export_channel_day -v`

## Turn 83 | 2026-04-12

- `mirror reconcile-files` now persists the last run outcome in a local state file alongside other runtime-managed state.
- Plain output now shows a compact previous-run comparison, and `--json` now includes both the previous persisted payload and a computed delta block.
- This keeps reconcile repair batches auditable over time without adding a new database ownership path.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_cli -v`

## Turn 84 | 2026-04-12

- `user-env validate-live` and `user-env check-live` now surface the last persisted `mirror reconcile-files` result per workspace when that state exists.
- The live-health payload now carries reconcile evidence fields, and validation emits warning-class operator signals when the most recent reconcile batch recorded warnings or failures.
- This keeps hosted-file repair regressions visible in the normal managed-runtime operator path without turning reconcile history into a new hard health gate.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env -v`

## Turn 85 | 2026-04-12

- `user-env status` now exposes the latest persisted `mirror reconcile-files` summary per workspace in both plain output and `--json`.
- This gives lighter-weight dashboards and scripts access to repair-state evidence without invoking the full live validation gate.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env -v`

## Turn 86 | 2026-04-12

- Added API access to the lightweight managed-runtime status surface at `/v1/runtime/status`.
- The route exposes wrapper/service presence plus the latest persisted reconcile summary per workspace, so external monitoring can read repair-state evidence without shelling into `user-env`.
- Kept the transport thin by adding a small shared `runtime_status()` method in `slack_mirror.service.app` over the existing managed-runtime status builder.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_api_server tests.test_user_env -v`

## Turn 87 | 2026-04-12

- Added MCP parity for the lightweight managed-runtime status surface through `runtime.status`.
- This keeps CLI, API, and MCP aligned on the same persisted reconcile evidence instead of making agents special-case one transport.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_mcp_server tests.test_api_server tests.test_user_env -v`

## Turn 88 | 2026-04-13

- Added `scripts/render_runtime_report.py` as a generated runtime-report consumer over `/v1/runtime/status` and `/v1/runtime/live-validation`.
- The report renders either Markdown or HTML for point-in-time ops snapshots and review handoff, instead of forcing operators to work directly from raw JSON.
- Tightened the shared `validate_live_runtime()` service payload so API callers now receive the same reconcile and stale-suppression workspace fields already present in the underlying live-validation report.
- Updated the runtime and install docs so the new report script is part of the supported operator workflow.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_runtime_report tests.test_app_service tests.test_api_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 89 | 2026-04-13

- Added `slack-mirror user-env snapshot-report` as the supported managed-runtime command for persisting runtime snapshots into `~/.local/state/slack-mirror/runtime-reports/`.
- Promoted the runtime-report renderer into shared service code so the script and the managed snapshot command use the same report generation path.
- Snapshot output now includes timestamped Markdown/HTML files plus stable `*.latest.md`, `*.latest.html`, and `*.latest.json` metadata files for review and handoff.
- Updated the live-ops and install docs so operators have a stable snapshot path instead of relying on ad hoc `/tmp` output.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_runtime_report tests.test_user_env tests.test_cli -v`
  - `./.venv/bin/python scripts/check_generated_docs.py`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 90 | 2026-04-13

- Added managed `slack-mirror-runtime-report.service` and `slack-mirror-runtime-report.timer` units to the user-env install lifecycle.
- Install, update, and rollback now write the runtime-report units and enable the timer so scheduled snapshots continue without manual operator setup.
- `user-env status` now shows the managed runtime-report service and timer paths, and the status surface now includes timer units in the reported `services` map.
- Updated the live/install docs so the scheduled snapshot contract is explicit and operators know where to inspect the timer.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_runtime_report tests.test_user_env tests.test_cli -v`
  - `./.venv/bin/python scripts/check_generated_docs.py`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 91 | 2026-04-13

- Added bounded retention to the managed runtime-report snapshot writer under `runtime-reports/`.
- Timestamped Markdown/HTML snapshot pairs are now pruned automatically by age and count, while stable `*.latest.*` handoff files are preserved.
- Updated the live/install docs so operators know the retention contract instead of assuming timestamped snapshots accumulate forever.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_runtime_report -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 92 | 2026-04-13

- Added API publication for managed runtime snapshots through `/v1/runtime/reports`, `/v1/runtime/reports/{name}`, and direct latest HTML/MD/JSON serving under `/runtime/reports/`.
- Kept the existing `runtime-reports/` state directory canonical; this slice only adds browse/open paths over the existing managed snapshot artifacts.
- Updated the API/runtime/install docs so operators can open the latest report over `slack.localhost` instead of reading files from state manually.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 93 | 2026-04-13

- Added a browser-friendly runtime report index at `/runtime/reports` on top of the existing managed snapshot API routes.
- Kept the JSON listing and per-report routes unchanged; this is only a human browseability improvement over the already-published snapshot manifests.
- Updated the API/runtime/install docs so operators can start from a landing page instead of raw JSON when reviewing snapshots in a browser.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 94 | 2026-04-13

- Added stable latest-report aliases at `/v1/runtime/reports/latest` and `/runtime/reports/latest`.
- Kept the underlying snapshot manifests and named routes canonical; the new aliases simply resolve to the freshest available managed snapshot.
- Updated the API/runtime/install docs so operators have one stable URL for “latest runtime report” instead of having to know the current snapshot name.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 95 | 2026-04-13

- Added visual latest-report emphasis on the `/runtime/reports` browser index.
- The freshest snapshot row is now highlighted, badged, and linked through `/runtime/reports/latest`, while the named report routes remain unchanged.
- Updated the API/runtime/install docs so the browser index behavior is explicit for operators.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 96 | 2026-04-13

- Added header-level quick links on the `/runtime/reports` browser index for the latest HTML view and latest manifest.
- Kept the table and route model unchanged; this is only a faster operator jump path to the freshest managed snapshot.
- Updated the API/runtime/install docs so the new header links are part of the explicit browser contract.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 97 | 2026-04-13

- Added MCP parity for the common latest-runtime-report case through `runtime.report.latest`.
- Kept named runtime report browsing API-only; the MCP addition is intentionally narrow and only exposes the freshest managed snapshot manifest.
- Updated the transport contract docs so latest-report convenience is no longer browser/API-only.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_mcp_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 98 | 2026-04-13

- Reopened `P02` narrowly through `docs/dev/plans/0009-2026-04-13-frontend-auth-baseline.md` for browser-surface auth hardening.
- Added a bounded local-password frontend-auth baseline modeled on the lighter parts of `../litscout`:
  - auth users, credentials, and sessions now live in the canonical SQLite DB
  - browser sessions are cookie-backed
  - `/auth/status`, `/auth/session`, `/auth/register`, `/auth/login`, and `/auth/logout` are now real
  - `/login` and `/register` now exist as minimal HTML entry pages
- Protected browser-facing export/runtime-report surfaces when frontend auth is enabled:
  - unauthenticated HTML requests redirect to `/login`
  - unauthenticated protected JSON requests fail with `AUTH_REQUIRED`
- Kept the scope intentionally narrow:
  - health and non-browser ingress paths remain outside this gate
  - no provider/OAuth auth was added in this first slice
- Updated `README.md`, `docs/CONFIG.md`, and `docs/API_MCP_CONTRACT.md` so the config and route contract are explicit.
- Validation:
  - `python -m py_compile slack_mirror/service/api.py slack_mirror/service/app.py slack_mirror/service/frontend_auth.py slack_mirror/core/db.py tests/test_api_server.py tests/test_frontend_auth.py`
  - `./.venv/bin/python -m unittest tests.test_api_server tests.test_frontend_auth -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

- Follow-up hardening in the same slice:
  - replaced the single global cookie-secure boolean with `cookie_secure_mode`
  - `auto` now prefers browser origin/referrer scheme, then reverse-proxy proto headers, and finally configured local/external host mapping
  - this keeps `http://slack.localhost` usable while allowing HTTPS ingress to receive `Secure` cookies
  - cooper local ingress now splits `.localhost` and external-host routing so the external-host path restores HTTPS-forwarded headers before handing the request to the app

## Turn 99 | 2026-04-13

- Added a real authenticated browser landing page at `/` instead of leaving the root path as a 404.
- Kept the page thin over existing owned surfaces:
  - runtime status
  - runtime report manifests
  - managed export manifests
- Kept frontend-auth behavior coherent:
  - anonymous `GET /` now redirects to `/login?next=%2F`
  - authenticated users land on a compact browser home with quick links, runtime health, recent reports, and recent exports
- Updated the repo docs so `/` is now part of the explicit browser contract, not an accidental implementation detail.
- Validation:
  - `python -m py_compile slack_mirror/service/app.py slack_mirror/service/api.py tests/test_api_server.py`
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 100 | 2026-04-13

- Tightened the browser auth baseline with same-origin CSRF protection for:
  - `/auth/register`
  - `/auth/login`
  - `/auth/logout`
- The auth POST routes now require a matching `Origin` or `Referer` header and fail with `CSRF_FAILED` on cross-origin or headerless requests.
- Kept the hardening bounded:
  - no separate CSRF token store
  - no new frontend state model
  - no changes to non-browser API routes
- Updated the browser-auth docs and the active `0009` plan so the remaining work is now session ergonomics and registration policy, not first-pass CSRF posture.
- Validation:
  - `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 101 | 2026-04-13

- Added bounded browser-session ergonomics on top of the local frontend-auth baseline:
  - `GET /auth/sessions`
  - `POST /auth/sessions/<id>/revoke`
- Kept the surface narrow and ownership-safe:
  - session listing is scoped to the authenticated user
  - revocation only succeeds for sessions owned by that user
  - revoking the current session clears the browser cookie as part of the same response
- Kept the same-origin CSRF rule for the new revoke route instead of introducing a second browser-write policy.
- Updated the auth docs and active `0009` plan so remaining work is now mostly UX and live-registration policy, not missing revocation plumbing.
- Validation:
  - `python -m py_compile slack_mirror/core/db.py slack_mirror/service/frontend_auth.py slack_mirror/service/app.py slack_mirror/service/api.py tests/test_api_server.py`
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 102 | 2026-04-13

- Added an explicit frontend-auth registration allowlist so self-registration can be limited to specific normalized usernames instead of remaining fully open whenever `allow_registration` is true.
- The new config field is `service.auth.registration_allowlist`, and it accepts email-style usernames such as `ecochran76@gmail.com`.
- Kept the policy narrow:
  - login behavior is unchanged for existing local users
  - registration still uses the current local username/password model
  - the allowlist only constrains who may create new local accounts
- Updated the active `0009` plan and auth/config docs so the new registration-policy seam is part of the documented browser-auth contract.
- Validation:
  - `python -m py_compile slack_mirror/service/frontend_auth.py slack_mirror/service/app.py tests/test_api_server.py`
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 103 | 2026-04-13

- Added `/settings` as the first browser-facing consumer of the frontend-auth session-management seam.
- Kept the page thin over existing owned surfaces:
  - frontend-auth policy from `/auth/status`
  - current-user sessions from `/auth/sessions`
  - revocation through `POST /auth/sessions/<id>/revoke`
- Wired the settings page into the authenticated landing page so browser users no longer need to hand-call auth JSON routes just to inspect policy or revoke sessions.
- Validation:
  - `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - live smoke on `http://slack.localhost/settings`

## Turn 104 | 2026-04-13

- Tightened the browser registration UX so `/register` now shows the live allowlist policy instead of presenting the identity field as an unconstrained generic username.
- When `service.auth.registration_allowlist` is set, the register page now:
  - labels the field as `Allowed email or username`
  - lists the allowed identities
  - tells the user to use one of those exact values
- Kept the backend contract unchanged; this slice is presentation and operator clarity, not a new auth model.
- Validation:
  - `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - live smoke on `http://slack.localhost/register`

## Turn 105 | 2026-04-13

- Tightened login UX parity so `/login` now labels the identity field as `Email or username`, matching the allowlisted registration language already shown on `/register`.
- Kept this slice deliberately narrow: copy and browser contract only, with no backend auth-model changes.
- Validation:
  - `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - live smoke on `http://slack.localhost/login`

## Turn 106 | 2026-04-13

- Removed the settings-page full reload after successful session revocation.
- `/settings` now updates the revoked session row inline and only redirects to `/login` when the current browser session is the one being revoked.
- Kept the backend contract unchanged; this is browser UX refinement over the existing auth routes.
- Validation:
  - `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - live smoke on `http://slack.localhost/settings`

## Turn 107 | 2026-04-13

- Closed `0009-2026-04-13-frontend-auth-baseline.md`.
- Closed `P02` in `ROADMAP.md`.
- Closure basis:
  - local password-based browser auth is shipped
  - protected browser-facing export and runtime-report routes are shipped
  - same-origin browser write protection is shipped
  - current-user session listing and revocation are shipped
  - authenticated landing and settings pages are shipped
  - allowlist-aware registration and reason-aware login UX are shipped
- Any future auth or browser-surface work should reopen as a new narrow child plan instead of extending `0009`.
- Validation:
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 108 | 2026-04-13

- Opened and closed `0010-2026-04-13-frontend-auth-hardening.md` as a narrow `P02` child slice.
- Tightened `/auth/status` so allowlisted registration is no longer reported as fully open registration.
- Added bounded failed-login throttling at the shared frontend-auth boundary with config-backed window and threshold controls.
- The login throttle now returns a stable `429 RATE_LIMITED` error with retry metadata instead of only repeating generic invalid-credential errors.
- Validation:
  - `python -m py_compile slack_mirror/core/db.py slack_mirror/service/errors.py slack_mirror/service/frontend_auth.py slack_mirror/service/app.py slack_mirror/service/api.py tests/test_api_server.py`
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 109 | 2026-04-13

- Opened and closed `0011-2026-04-13-frontend-auth-idle-timeout.md` as a narrow `P02` child slice.
- Added a config-backed inactivity timeout for browser-auth sessions on top of absolute session expiry.
- Enforced idle expiry through the shared frontend-auth session resolver instead of only at individual browser routes.
- Updated session listing and auth status so the idle-timeout policy is visible to operators and browser consumers.
- Validation:
  - `python -m py_compile slack_mirror/service/frontend_auth.py slack_mirror/service/app.py tests/test_api_server.py`
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 110 | 2026-04-13

- Opened and closed `0012-2026-04-13-frontend-auth-settings-governance.md` as a narrow `P02` child slice.
- Extended `/settings` so the active browser-auth policy is visible in the browser instead of only through `/auth/status`.
- The settings page now shows registration mode, allowlist count, absolute session lifetime, idle timeout, and login-throttle policy.
- Validation:
  - `python -m py_compile slack_mirror/service/api.py tests/test_api_server.py`
  - `./.venv/bin/python -m unittest tests.test_api_server -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Turn 111 | 2026-04-13

- Opened and closed `0013-2026-04-13-frontend-auth-live-defaults.md` as a narrow `P02` child slice.
- Tightened the shipped config template so browser self-registration now defaults to off for new installs.
- Added a live-validation warning for externally exposed installs that explicitly keep browser self-registration enabled.
- Validation:
  - `./.venv/bin/python -m unittest tests.test_user_env -v`
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
