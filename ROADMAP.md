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

Legacy context:
- `docs/dev/PHASE_1_PLATFORM_FOUNDATION.md`
- `docs/dev/INSTALLER_UPGRADE_PLAN.md`
- `docs/dev/RELEASE_POLICY.md`

## P02 | Service Surfaces

Status: PLANNED

Purpose:
- define and harden the shared application boundary for CLI, API, MCP, and skills

Actionable plans:
- `docs/dev/plans/0003-2026-04-09-api-mcp-boundary.md`

Legacy context:
- `docs/dev/API_MCP_BOUNDARY.md`

## P03 | Search And Evaluation

Status: PLANNED

Purpose:
- keep search, evaluation, and search-platform reuse on a bounded roadmap lane

Legacy context:
- `docs/dev/PHASE_E_SEMANTIC_SEARCH.md`
- `docs/dev/PHASE_F_SEARCH_PLATFORM.md`
- `docs/dev/SEARCH_EVAL.md`
- `docs/dev/DAILY_BRIEFING_HARDENING_PLAN.md`

## P04 | Live Ops And Runtime Hardening

Status: PLANNED

Purpose:
- keep live-mode operations, auth guardrails, user install, and daemon drift checks coherent

Legacy context:
- `docs/dev/LIVE_MODE.md`
- `docs/dev/AUTH_GUARDRAILS.md`
- `docs/dev/USER_INSTALL.md`

## P05 | Outbound Messaging And Listeners

Status: PLANNED

Purpose:
- make outbound messaging and listener/hook workflows first-class platform capabilities

No actionable plan is open yet. Open one under `docs/dev/plans/` before implementation work starts on this lane.
