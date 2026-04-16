# Tenant Onboarding Wizard And Settings

State: OPEN
Roadmap: P09
Opened: 2026-04-15
Follows:
- `docs/dev/plans/0048-2026-04-15-install-onboarding-and-manifest-hardening.md`
- `docs/dev/plans/0049-2026-04-15-polymer-tenant-onboarding.md`

## Scope

Build a guided tenant/workspace onboarding path that can take an operator from tenant intent to a verified, live workspace with less manual config editing.

This plan covers:

- one-shot CLI wizard for adding a tenant/workspace
- reusable shared service primitives for tenant config status, scaffold creation, credential readiness, activation, and validation
- browser settings expansion for tenant management and onboarding status
- JSON Slack app manifest generation and presentation from the product surface
- safe handoff points for credentials that must still be copied from Slack
- validation and rollback behavior for partially completed onboarding

This plan does not include:

- inventing, storing in git, or displaying Slack secrets
- bypassing Slack's app-creation or workspace-authorization UI
- automatically enabling a tenant before required credentials pass verification
- replacing the existing managed config file as the source of truth in this slice
- changing the existing `default` or `soylei` tenant behavior

## Current State

- the managed install supports multiple configured workspaces under `~/.config/slack-mirror/config.yaml`
- workspace config can be synced into the DB with `slack-mirror-user workspaces sync-config`
- workspace readiness can be checked with `workspaces verify --require-explicit-outbound` and `user-env check-live`
- disabled workspace scaffolds are now supported and skipped by default verification
- Polymer is scaffolded as a disabled workspace with explicit `SLACK_POLYMER_*` placeholders
- the operator-facing Slack app manifest path now prefers JSON:
  - `manifests/slack-mirror-socket-mode.json`
  - `manifests/slack-mirror-socket-mode-polymer.rendered.json`
- the first reusable onboarding slice is now implemented:
  - shared redacted tenant status and config mutation service
  - `slack-mirror tenants status`
  - `slack-mirror tenants onboard`
  - `slack-mirror tenants credentials`
  - protected `GET /v1/tenants`
  - protected `POST /v1/tenants/onboard`
  - protected `POST /v1/tenants/<name>/credentials`
  - protected `POST /v1/tenants/<name>/activate`
  - protected `POST /v1/tenants/<name>/live`
  - protected `POST /v1/tenants/<name>/backfill`
  - protected `POST /v1/tenants/<name>/retire`
  - browser tenant onboarding surface at `/settings/tenants`
- browser `/settings` covers browser-auth policy and session management, with tenant management split to `/settings/tenants`
- browser `/v1/workspaces` still lists DB-synced workspaces only; tenant onboarding state now lives under `/v1/tenants`
- `slack-mirror tenants activate` now blocks until required credentials are present, enables the tenant, syncs DB state, and can invoke the product-owned live-unit wrapper over:
  - `scripts/install_live_mode_systemd_user.sh <workspace>`
- browser activation is available for credential-ready disabled tenants through `/settings/tenants`
- credential installation is now available through the CLI and `/settings/tenants`; it writes only to the configured dotenv file, backs up existing dotenv content, and reports installed variable names without echoing secret values
- `/settings/tenants` now exposes live-sync start/restart/stop controls, a bounded backfill action, and a guarded retire flow with optional DB-row deletion
- Polymer activation is still blocked because Polymer credentials are not present yet

## Target Operator Experience

CLI path:

```bash
slack-mirror-user tenants onboard \
  --name polymer \
  --domain polymerconsul-clo9441 \
  --display-name "Polymer Consulting Group"
```

The wizard should:

- validate the requested tenant name and Slack domain
- render a tenant-specific JSON Slack app manifest
- show the manifest path and Slack app creation steps
- scaffold a disabled workspace block with deterministic env placeholders
- show exactly which credentials are needed and where to store them
- sync the disabled workspace into the DB
- verify active workspaces remain healthy
- stop at a clear `credentials_required` checkpoint until the operator has copied secrets into the configured dotenv file

After credentials are present:

```bash
slack-mirror-user tenants credentials polymer \
  --credential token=xoxb-... \
  --credential outbound_token=xoxb-... \
  --credential app_token=xapp-... \
  --credential signing_secret=...
slack-mirror-user tenants activate polymer
```

The activation command should:

- re-read config and dotenv values
- verify credential presence without printing secret values
- set the workspace enabled only after verification passes
- sync config into the DB
- install or refresh per-workspace live units
- run targeted workspace verification and `user-env check-live`
- print the browser settings URL for follow-up review

Browser path:

- `/settings` should gain a tenant management section or link to `/settings/tenants`
- operators should see configured tenants, enabled/disabled state, DB-sync state, credential-readiness state, live-unit state, and latest validation summary
- onboarding should present the JSON manifest and credential checklist without exposing secret values
- unsafe mutations should require explicit browser-auth and same-origin checks, matching existing manager pages
- activation from the browser should be limited to state transitions and validation; secret entry should either be avoided or use a local-only, redacted write path with clear storage semantics
- tenant retirement should be guarded by explicit name confirmation and a separate DB-deletion intent

## Implementation Tracks

### Track A | Shared Onboarding Model

- add a shared tenant-onboarding service module that can inspect config, dotenv, DB sync, live-unit state, and validation state
- define a machine-readable tenant status shape with fields for:
  - `name`
  - `domain`
  - `team_id_present`
  - `enabled`
  - `db_synced`
  - `credential_placeholders`
  - `credential_presence`
  - `manifest_path`
  - `live_units`
  - `validation_status`
  - `next_action`
- keep secret values redacted at the model boundary

### Track B | Config Mutation Safety

- implement narrow config mutation helpers for adding a disabled workspace scaffold and toggling `enabled`
- create timestamped backups before mutating `~/.config/slack-mirror/config.yaml`
- preserve unrelated config formatting as much as practical, but favor valid YAML over cosmetic preservation
- validate config after every mutation before writing or before activation completes
- make reruns idempotent for an existing scaffold with the same name/domain

### Track C | CLI Wizard

- add a CLI command group, likely `tenants`, over shared service primitives
- first commands:
  - `tenants onboard`
  - `tenants status`
  - `tenants activate`
- support `--dry-run` and `--json` for automation and testability
- print concise step-by-step operator guidance, including the Slack app manifest path and dotenv destination
- never echo secret values

Status:

- shipped for `status`, `onboard`, `credentials`, and `activate`

### Track D | Browser Settings Surface

- expand settings navigation with a tenant-management page
- add protected API routes for tenant status and safe onboarding actions
- render tenant cards with activation state, credential readiness, live-unit status, and next action
- add a guided onboarding panel that can generate or link the rendered JSON manifest
- add a credential install form that writes to the configured local dotenv without rendering stored secrets
- add guarded retire, live-sync, and bounded backfill controls to the tenant cards
- reuse existing browser helper patterns for busy states, row-local errors, and same-origin mutation checks

Status:

- shipped for redacted status, scaffold creation, local credential installation, credential-ready activation, live-sync controls, bounded backfill, and guarded retirement

### Track E | Live Activation Integration

- wrap per-workspace live-unit installation in a product-owned command path instead of requiring the operator to remember the repo script
- keep activation staged:
  - scaffold disabled
  - credentials present
  - verify
  - enable
  - install or refresh units
  - live validation
- make failed activation recoverable by leaving the workspace disabled unless the enable step has already passed verification

Status:

- activation now blocks before enabling when required credentials are missing
- live-unit installation is wrapped by the tenant activation service and can be skipped for tests or staged manual activation
- remaining work is a real credential-backed activation rehearsal

### Track F | Documentation And Rehearsal

- update `docs/dev/USER_INSTALL.md`, `docs/CONFIG.md`, and `docs/SLACK_MANIFEST.md` after behavior lands
- update `README.md` when the wizard becomes the recommended path
- rehearse against Polymer without exposing credentials
- record the exact validation transcript in the runbook

## Critical Path

1. Define tenant status and config mutation primitives.
2. Ship CLI `tenants status` and `tenants onboard --dry-run`.
3. Ship real disabled scaffold creation through the CLI wizard.
4. Add activation command after credential-presence checks are deterministic. Shipped.
5. Add browser read-only tenant status to settings. Shipped.
6. Add browser onboarding and activation actions after the shared mutation path is proven. Shipped.
7. Add a safe product-owned credential installation step so operators do not hand-edit dotenv syntax. Shipped.
8. Add tenant-management hardening from live onboarding feedback: clearer ready-to-activate state, live controls, bounded backfill, and guarded retire/delete. Shipped.
9. Promote the wizard to the canonical docs path. Shipped for scaffold, credential, activation, live, backfill, and retire commands.
10. Rehearse a real credential-backed activation and close or narrow this lane.

## Acceptance Criteria

- a new tenant can be scaffolded with one command without manually editing `config.yaml`
- the wizard renders or points to a tenant-specific JSON Slack app manifest
- the wizard tells the operator exactly which Slack UI pages produce each required credential
- the wizard can install copied Slack credentials into the configured dotenv file without printing secret values
- credentials are checked for presence without printing secret values
- activation is blocked until required credentials are present
- activation can enable the tenant, sync DB state, install live units, and run validation
- `/settings` or `/settings/tenants` shows tenant onboarding and runtime state from the same shared model
- `/settings/tenants` can start/restart/stop live sync, launch a bounded backfill, and retire a tenant through guarded confirmation
- existing active workspaces remain unaffected by a disabled or failed new-tenant scaffold

## Validation Plan

- unit tests for tenant status, config mutation, idempotent reruns, and redaction
- CLI tests for `tenants onboard --dry-run`, scaffold creation, credential installation, status JSON, and activation blocking
- API tests for protected tenant-management routes
- browser HTML/API smoke for the settings tenant page
- targeted live rehearsal with Polymer:
  - scaffold
  - credential checkpoint
  - activation after credentials
  - `slack-mirror-user user-env check-live --json`
- planning audit:
  - `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
