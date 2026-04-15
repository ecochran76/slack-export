# Install Onboarding And Manifest Hardening

State: OPEN
Roadmap: P07
Opened: 2026-04-15
Follows:
- `docs/dev/plans/0005-2026-04-10-live-ops-runtime-hardening.md`
- `docs/dev/plans/0014-2026-04-13-frontend-auth-bootstrap-provisioning.md`

## Scope

Make new-user installation and first-workspace onboarding fast, well explained, and auditable.

This plan is specifically about:

- giving the repo one canonical operator path from fresh install to first usable workspace
- reducing documentation sprawl across install, config, live-mode, and auth-bootstrap surfaces
- reviewing the shipped JSON manifests for accuracy, contract clarity, and scope adequacy
- tightening manifest schemas where current payloads are too thin for onboarding signoff or downstream tooling

This plan is not a generic reopening of broader platform, frontend, or search lanes.

## Current State

- user-scope install, update, rollback, uninstall, status, validate-live, check-live, recover-live, and snapshot-report flows already exist through `slack-mirror user-env`
- the repo now has one canonical fresh-install-to-first-workspace operator path in `docs/dev/USER_INSTALL.md`, with `README.md`, `docs/CONFIG.md`, and `docs/dev/LIVE_MODE.md` aligned to that route instead of acting as competing entrypoints
- workspace configuration, live-mode topology, and frontend-auth bootstrap are documented, but the operator journey is split across:
  - `README.md`
  - `docs/dev/USER_INSTALL.md`
  - `docs/CONFIG.md`
  - `docs/dev/LIVE_MODE.md`
  - `docs/CLI.md`
- export manifests now carry explicit schema, generation time, producer, and provenance metadata, and the contract doc now describes the exact file-entry shape exposed through the API
- runtime report manifests now carry explicit schema, generation time, producer, provenance, and compact machine-readable validation summary fields suitable for onboarding signoff and downstream automation
- the repo already has live JSON manifest surfaces for:
  - export manifests through `/v1/exports` and `/v1/exports/{export_id}`
  - runtime report manifests through `/v1/runtime/reports` and `/v1/runtime/reports/latest`
  - managed runtime status through `/v1/runtime/status`

## Remaining Work

### Track A | Canonical New-User Path

- shipped baseline:
  - one canonical quickstart now covers fresh user install, first config edit, workspace sync and verification, per-workspace live unit install, operator smoke gate, frontend user bootstrap, first browser smoke, and runtime snapshot signoff
- remaining work:
  - decide whether `docs/CLI.md` needs a dedicated onboarding pointer near `user-env` and `workspaces`
  - verify the quickstart against a true cold-start rehearsal instead of only a docs/code audit

### Track B | Tenant / Workspace Onboarding Flow

- shipped baseline:
  - docs now distinguish first-workspace vs additional-workspace onboarding explicitly
  - docs now distinguish per-install vs per-workspace steps explicitly
  - config docs now distinguish read-path, write-path, and ingress-path credentials
  - user-facing docs now treat `workspace` as the canonical runtime term and reconcile tenant-style language to that term
- remaining work:
  - verify that additional workspace onboarding is friction-light in practice during a real operator rehearsal

### Track C | JSON Manifest Audit

- shipped baseline:
  - export manifests were audited against emitted payloads and the API contract doc now records both top-level and file-entry shapes
  - runtime report manifests were audited against emitted payloads and now expose compact machine-readable validation summary fields directly in the manifest
- remaining work:
  - verify the upgraded manifest shape against a colder operator workflow instead of only unit/API tests

### Track D | Contract Hardening

- shipped baseline:
  - both manifest families now include `schema_version`, `generated_at`, `producer`, and provenance metadata
  - `docs/API_MCP_CONTRACT.md` now documents the exact runtime-report and export manifest shapes, including runtime validation summary fields and export file-entry fields
  - targeted tests now lock the upgraded emitted manifest schemas across runtime-report, app-service, and API surfaces
- remaining work:
  - keep future manifest changes narrow and version-aware if the contract has to grow again

### Track E | Friction Removal

- identify the highest-friction setup steps and either:
  - simplify them
  - or document them much more directly
- likely candidates include:
  - first config editing
  - first frontend-user bootstrap
  - differentiating install-time validation vs full live validation
  - understanding which JSON/status surface to trust for onboarding signoff

## Non-Goals

- redesigning the whole config model
- reopening the browser search lane
- adding a hosted multi-tenant control plane
- broad renaming of internal workspace concepts unless onboarding language truly requires it
- changing service boundaries outside the existing `slack_mirror.service.app` ownership seam

## Acceptance Criteria

- the repo has one explicit open plan for install/onboarding and manifest hardening
- the plan makes the canonical fresh-install-to-first-workspace path explicit
- the manifest audit scope clearly covers both export and runtime-report JSON surfaces
- follow-up code/doc work can proceed in bounded slices without mixing onboarding UX, manifest schema, and unrelated platform work
- the roadmap and runbook are wired so this lane is auditable by the planning helper

## Next Implementation Slices

1. Rehearse the updated onboarding path from a colder starting point and trim any remaining friction that the manifest audit does not already cover.
2. Decide whether `docs/CLI.md` should gain a short explicit onboarding pointer near `user-env` and `workspaces`.
3. Keep any further manifest growth as separate bounded slices only if a downstream consumer proves the current schema is still insufficient.

## Validation

- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git status --short`
