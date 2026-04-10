# Slack Export Roadmap

This file is the master plan for repository-level priorities.

Planning rules:
- Revise this file cautiously.
- Do not materially reorder, rename, or reprioritize roadmap lanes unless the user explicitly asks for that change or a narrow correction is required to reflect already-requested work.
- Treat this file as the authoritative priority map.
- Treat `RUNBOOK.md` as the dated turn log of what happened.
- Treat actionable plan files under `docs/dev/plans/` as the bounded implementation plans.

## P01 | Platform Foundation

Status: OPEN

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
- release/version discipline is partially documented and partially implemented
- remaining work is making installer validation, rollback, and release policy fully explicit and auditable

Legacy context:
- retained through the dated runbook and prior local planning notes when needed for archaeology

## P02 | Service Surfaces

Status: OPEN

Purpose:
- define and harden the shared application boundary for CLI, API, MCP, and skills

Actionable plans:
- `docs/dev/plans/0003-2026-04-09-api-mcp-boundary.md`

Current state:
- shared application-service layer exists
- local API server exists
- MCP server exists
- remaining work is contract hardening, surface expansion, and operator discipline

Legacy context:
- retained through the dated runbook and prior local planning notes when needed for archaeology

## P03 | Search And Evaluation

Status: PLANNED

Purpose:
- keep search, evaluation, and search-platform reuse on a bounded roadmap lane

Current state:
- keyword and semantic search exist
- embedding backlog discipline and SQLite contention hardening have landed
- remaining work is evaluation, search freshness policy, and search-platform reuse boundaries

Legacy context:
- `docs/dev/PHASE_E_SEMANTIC_SEARCH.md`
- `docs/dev/PHASE_F_SEARCH_PLATFORM.md`
- `docs/dev/SEARCH_EVAL.md`
- `docs/dev/DAILY_BRIEFING_HARDENING_PLAN.md`

## P04 | Live Ops And Runtime Hardening

Status: OPEN

Purpose:
- keep live-mode operations, auth guardrails, user install, and daemon drift checks coherent

Actionable plans:
- `docs/dev/plans/0005-2026-04-10-live-ops-runtime-hardening.md`

Current state:
- supported live topology is documented
- install/status scripts exist
- auth guardrails and explicit outbound validation exist
- remaining work is hardening operational checks, service supervision, and drift detection into a clearly bounded operator contract

Legacy context:
- `docs/dev/LIVE_MODE.md`
- `docs/dev/AUTH_GUARDRAILS.md`
- `docs/dev/USER_INSTALL.md`

## P05 | Outbound Messaging And Listeners

Status: OPEN

Purpose:
- make outbound messaging and listener/hook workflows first-class platform capabilities

Actionable plans:
- `docs/dev/plans/0004-2026-04-09-outbound-listeners-hardening.md`

Current state:
- outbound send and thread-reply flows exist through the shared service
- listener registration, delivery inspection, and delivery acknowledgement exist
- remaining work is hardening the contract, delivery model, and operator-facing policy
