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
- the repo already has live JSON manifest surfaces for:
  - export manifests through `/v1/exports` and `/v1/exports/{export_id}`
  - runtime report manifests through `/v1/runtime/reports` and `/v1/runtime/reports/latest`
  - managed runtime status through `/v1/runtime/status`
- current export manifests are useful for internal browser/API usage but remain thin for onboarding/audit use:
  - no explicit schema version
  - no generation timestamp
  - no producer/version metadata
  - no provenance field clarifying current-service URL reconstruction vs original bundle metadata
- current runtime report manifests are also thin:
  - status and summary are present
  - file paths are present
  - machine-readable validation detail is not surfaced directly in the manifest
  - no explicit schema/version metadata exists for downstream consumers

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

- review export manifests for:
  - accuracy against emitted payloads
  - field naming clarity
  - file-entry contract completeness
  - suitability for downstream automation and onboarding review
- review runtime report manifests for:
  - accuracy against emitted payloads
  - adequacy as a machine-readable onboarding or runtime signoff artifact
  - whether validation summary/detail needs to be promoted into the manifest

### Track D | Contract Hardening

- add explicit schema metadata to manifest payloads where justified
- document exact JSON route shapes in `docs/API_MCP_CONTRACT.md`, not just top-level summary fields
- add or tighten tests that lock the emitted manifest schemas

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

1. Audit the current export and runtime-report manifest payloads against real emitted JSON and document the exact contract gaps.
2. Land the smallest justified schema-hardening patch for manifest versioning/provenance, with tests and contract-doc updates in the same slice.
3. Rehearse the updated onboarding path from a colder starting point and trim any remaining friction that the manifest audit does not already cover.

## Validation

- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git status --short`
