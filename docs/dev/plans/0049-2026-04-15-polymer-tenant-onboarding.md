# Polymer Tenant Onboarding

State: OPEN
Roadmap: P08
Opened: 2026-04-15
Follows:
- `docs/dev/plans/0048-2026-04-15-install-onboarding-and-manifest-hardening.md`

## Scope

Onboard Polymer Consulting Group as a new Slack Mirror workspace/tenant.

Target Slack URL:

- `https://polymerconsul-clo9441.slack.com`

Local workspace name:

- `polymer`

This plan covers:

- safe managed-config scaffolding
- credential readiness checks
- workspace DB sync
- live unit activation after credentials exist
- validation and browser/API smoke after activation

This plan does not include exfiltrating or inventing Slack credentials.

## Current State

- the managed install is live with `default` and `soylei` active
- Polymer has been added to `~/.config/slack-mirror/config.yaml` as a disabled scaffold
- the Polymer scaffold uses explicit environment placeholders:
  - `SLACK_POLYMER_TEAM_ID`
  - `SLACK_POLYMER_BOT_TOKEN`
  - `SLACK_POLYMER_WRITE_BOT_TOKEN`
  - `SLACK_POLYMER_USER_TOKEN`
  - `SLACK_POLYMER_WRITE_USER_TOKEN`
  - `SLACK_POLYMER_APP_TOKEN`
  - `SLACK_POLYMER_SIGNING_SECRET`
- no Polymer credential env vars were present in the current shell during the first rehearsal
- `slack-mirror-user workspaces sync-config` inserted the disabled Polymer workspace into the managed DB
- `slack-mirror-user user-env check-live --json` still passed for the active workspaces
- a verifier gap was found: `workspaces verify --require-explicit-outbound` checked disabled workspaces
- the repo code now skips disabled workspaces by default and reports `<workspace>\tdisabled` when a disabled workspace is explicitly selected
- the managed install has been updated from the repo so `slack-mirror-user` now has that verifier behavior live
- default verification now skips Polymer:
  - `slack-mirror-user workspaces verify --require-explicit-outbound`
- explicit Polymer verification now reports:
  - `polymer	disabled`
- `slack-mirror-user user-env check-live --json` passes with the pre-existing `EMBEDDING_PENDING` warning for `default`
- the Slack app manifest workflow now documents the credential acquisition path and the Polymer rendered manifest path:
  - `manifests/slack-mirror-socket-mode-polymer.rendered.json`

## Remaining Work

### Track A | Credential Readiness

- create the Polymer Slack app at `https://api.slack.com/apps` from:
  - `manifests/slack-mirror-socket-mode-polymer.rendered.json`
- obtain or configure the Polymer Slack credentials:
  - team ID
  - bot read token
  - bot write token
  - user read token, if user-auth backfill is required
  - user write token, if user write actions are required
  - app-level Socket Mode token
  - signing secret
- store them in the configured dotenv source or environment without committing secrets
  - current managed dotenv source: `~/credentials/API-keys.env`

### Track B | Activation

- set Polymer `enabled: true` after credentials are present
- run `slack-mirror-user workspaces sync-config`
- run `slack-mirror-user workspaces verify --workspace polymer --require-explicit-outbound`
- install live units with `scripts/install_live_mode_systemd_user.sh polymer`

### Track C | Validation

- run `slack-mirror-user user-env check-live --json`
- inspect `systemctl --user status slack-mirror-webhooks-polymer.service slack-mirror-daemon-polymer.service`
- inspect logs if either unit is not active
- run a small search/status smoke after Polymer has mirrored data

## Non-Goals

- changing the tenant naming model
- changing Slack app scopes
- making Polymer active without credentials
- disabling or modifying existing `default` or `soylei` live units

## Acceptance Criteria

- Polymer is represented in managed config and DB without breaking existing active workspace validation
- disabled workspace scaffolds do not poison default `workspaces verify`
- after credentials are present, Polymer can be enabled, verified, started, and included in `check-live`

## Validation

- `uv run python -m unittest tests.test_status_and_verify.StatusAndVerifyTests.test_workspaces_verify_can_require_explicit_outbound_tokens tests.test_status_and_verify.StatusAndVerifyTests.test_workspaces_verify_passes_with_explicit_outbound_tokens tests.test_status_and_verify.StatusAndVerifyTests.test_workspaces_verify_skips_disabled_workspaces_by_default tests.test_status_and_verify.StatusAndVerifyTests.test_workspaces_verify_reports_disabled_when_explicitly_selected -v`
- `python -m py_compile slack_mirror/cli/main.py tests/test_status_and_verify.py`
- `slack-mirror-user workspaces sync-config`
- `slack-mirror-user user-env check-live --json`
- `uv run slack-mirror user-env update`
- `slack-mirror-user workspaces verify --require-explicit-outbound`
- `slack-mirror-user workspaces verify --workspace polymer --require-explicit-outbound`
