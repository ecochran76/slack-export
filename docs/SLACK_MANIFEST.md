# Slack App Manifest Workflow (Private Multi-Workspace)

Use one manifest template and create one private app per workspace (no public distribution review).
For live Slack Mirror installs, prefer the Socket Mode manifest so the local service does not need a public Slack Events request URL.

## Files

- Preferred live-mode template: `manifests/slack-mirror-socket-mode.json`
- YAML equivalent: `manifests/slack-mirror-socket-mode.yaml`
- Legacy HTTP-events template: `manifests/slack-app.yaml`
- Renderer: `scripts/render_slack_manifest.py`
- Rendered output examples:
  - `manifests/slack-mirror-socket-mode.rendered.json`
  - `manifests/slack-app.rendered.yaml`
- Polymer rendered manifest:
  - `manifests/slack-mirror-socket-mode-polymer.rendered.json`
- PCG rendered manifest:
  - `manifests/slack-mirror-socket-mode-pcg.rendered.json`

Prefer JSON for Slack's copy/paste app-manifest flow. YAML is supported by Slack, but JSON is less brittle in browser text areas and chat/terminal copy paths.

## 1) Render a workspace-specific manifest

For a managed install, prefer the tenant wizard because it renders the JSON manifest and creates a disabled workspace scaffold in one step:

```bash
slack-mirror-user tenants onboard \
  --name polymer \
  --domain polymerconsul-clo9441 \
  --display-name "Polymer Consulting Group"
```

The same flow is available from the authenticated browser settings page:

- `http://slack.localhost/settings/tenants`

After the required credentials are installed into the configured dotenv file, activate the tenant with:

```bash
slack-mirror-user tenants activate polymer
```

For a live Socket Mode workspace:

```bash
export SLACK_MIRROR_APP_NAME="Slack Mirror Polymer"
export SLACK_MIRROR_BOT_DISPLAY_NAME="Slack Mirror"
export SLACK_MIRROR_REDIRECT_URL="https://localhost:3000/slack/oauth/callback"

python3 scripts/render_slack_manifest.py \
  --template manifests/slack-mirror-socket-mode.json \
  --output manifests/slack-mirror-socket-mode-polymer.rendered.json
```

For the older HTTP Events API path, use `manifests/slack-app.yaml` and set `SLACK_EVENTS_URL` to a reachable HTTPS endpoint. The current live-mode topology uses Socket Mode instead.

## 2) Create the Slack app

1. Go to `https://api.slack.com/apps`.
2. Click **Create New App**.
3. Choose **From an app manifest**.
4. Select the target workspace.
5. Paste the rendered manifest JSON, for example `manifests/slack-mirror-socket-mode-polymer.rendered.json`.
6. Create the app.

## 3) Install the app and collect credentials

In the Slack app settings:

- **Basic Information**:
  - copy **Signing Secret** into `SLACK_<WORKSPACE>_SIGNING_SECRET`
  - note the app's workspace/team identifier if Slack shows it; otherwise obtain it with `auth.test` after token setup
- **OAuth & Permissions**:
  - click **Install to Workspace** or **Reinstall to Workspace**
  - copy **Bot User OAuth Token** (`xoxb-...`) into:
    - `SLACK_<WORKSPACE>_BOT_TOKEN`
    - `SLACK_<WORKSPACE>_WRITE_BOT_TOKEN`
  - if you enabled user scopes and installed user-token access, copy **User OAuth Token** (`xoxp-...`) into:
    - `SLACK_<WORKSPACE>_USER_TOKEN`
    - `SLACK_<WORKSPACE>_WRITE_USER_TOKEN`
- **Socket Mode**:
  - confirm Socket Mode is enabled by the manifest
  - create an app-level token with `connections:write`
  - copy the app-level token (`xapp-...`) into `SLACK_<WORKSPACE>_APP_TOKEN`

The canonical Socket Mode manifest now includes the outbound conversation scopes needed for MCP/API message sends by user reference:

- `channels:write`
- `groups:write`
- `im:write`
- `mpim:write`

If you update an existing app from an older manifest, reinstall the app after applying the new manifest so Slack grants the additional scopes.

For Polymer, use these variable names:

```bash
SLACK_POLYMER_TEAM_ID=
SLACK_POLYMER_BOT_TOKEN=
SLACK_POLYMER_WRITE_BOT_TOKEN=
SLACK_POLYMER_USER_TOKEN=
SLACK_POLYMER_WRITE_USER_TOKEN=
SLACK_POLYMER_APP_TOKEN=
SLACK_POLYMER_SIGNING_SECRET=
```

## 4) Install credentials

Do not put Slack secrets directly in tracked repo files.

For this managed install, `~/.config/slack-mirror/config.yaml` loads:

```yaml
dotenv: ~/credentials/API-keys.env
```

Prefer the product credential installer so onboarding does not require hand-editing dotenv syntax:

```bash
slack-mirror-user tenants credentials polymer \
  --credential team_id=T... \
  --credential token=xoxb-... \
  --credential outbound_token=xoxb-... \
  --credential user_token=xoxp-... \
  --credential outbound_user_token=xoxp-... \
  --credential app_token=xapp-... \
  --credential signing_secret=...
```

The accepted field names are `team_id`, `token`, `outbound_token`, `user_token`, `outbound_user_token`, `app_token`, and `signing_secret`.
The command maps them to the deterministic `SLACK_<WORKSPACE>_*` variables, writes or updates the configured dotenv file, creates a timestamped backup when replacing an existing file, and reports only redacted readiness.
It also accepts the env var names directly, for example `--credential SLACK_POLYMER_BOT_TOKEN=xoxb-...`.

The authenticated browser page at `http://slack.localhost/settings/tenants` provides the same local credential-install path.

Manual fallback for Polymer is to edit the dotenv file directly:

```bash
cat >> ~/credentials/API-keys.env <<'EOF'
SLACK_POLYMER_TEAM_ID=T...
SLACK_POLYMER_BOT_TOKEN=xoxb-...
SLACK_POLYMER_WRITE_BOT_TOKEN=xoxb-...
SLACK_POLYMER_USER_TOKEN=xoxp-...
SLACK_POLYMER_WRITE_USER_TOKEN=xoxp-...
SLACK_POLYMER_APP_TOKEN=xapp-...
SLACK_POLYMER_SIGNING_SECRET=...
EOF
```

If one token is intentionally shared for read and write, repeat the same value in both variables. Keeping separate variable names makes the read/write contract explicit and keeps `workspaces verify --require-explicit-outbound` meaningful.

## 5) Activate the workspace

Keep the workspace disabled until the credentials exist:

```yaml
workspaces:
  - name: polymer
    domain: polymerconsul-clo9441
    team_id: ${SLACK_POLYMER_TEAM_ID:-}
    token: ${SLACK_POLYMER_BOT_TOKEN:-}
    outbound_token: ${SLACK_POLYMER_WRITE_BOT_TOKEN:-}
    user_token: ${SLACK_POLYMER_USER_TOKEN:-}
    outbound_user_token: ${SLACK_POLYMER_WRITE_USER_TOKEN:-}
    app_token: ${SLACK_POLYMER_APP_TOKEN:-}
    signing_secret: ${SLACK_POLYMER_SIGNING_SECRET:-}
    enabled: false
```

After the env vars are present, prefer the activation command:

```bash
slack-mirror-user tenants activate polymer
```

That command sets `enabled: true`, syncs config into the DB, and installs or refreshes live units after required credentials are present.
Manual fallback:

```bash
slack-mirror-user workspaces sync-config
slack-mirror-user workspaces verify --workspace polymer --require-explicit-outbound
scripts/install_live_mode_systemd_user.sh polymer
slack-mirror-user user-env check-live --json
```

Repeat the same process for each workspace. Keep one manifest template; only rendered app name and credentials differ per workspace.
