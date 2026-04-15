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

- create one canonical quickstart that covers:
  - fresh user install
  - first config edit
  - workspace sync and verification
  - per-workspace live unit install
  - operator smoke gate
  - frontend user bootstrap
  - first browser/API smoke
- make the path opinionated enough that a new operator can reach first success without stitching multiple docs together manually

### Track B | Tenant / Workspace Onboarding Flow

- define the supported first-workspace and additional-workspace onboarding sequence explicitly
- clarify which steps are per-install vs per-workspace
- clarify which credentials are read-path vs write-path vs ingress-path requirements
- decide whether “tenant onboarding” should remain workspace terminology in user-facing docs or whether both terms need explicit reconciliation

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

1. Write a docs-first onboarding slice that produces one canonical operator quickstart for fresh install plus first workspace.
2. Audit the current export and runtime-report manifest payloads against real emitted JSON and document the exact contract gaps.
3. Land the smallest justified schema-hardening patch for manifest versioning/provenance, with tests and contract-doc updates in the same slice.

## Validation

- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git status --short`
