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
