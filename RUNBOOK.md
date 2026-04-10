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
