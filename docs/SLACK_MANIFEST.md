# Slack App Manifest Workflow (Private Multi-Workspace)

Use one manifest template and create one private app per workspace (no public distribution review).

## Files

- Template: `manifests/slack-app.yaml`
- Renderer: `scripts/render_slack_manifest.py`
- Rendered output (example): `manifests/slack-app.rendered.yaml`

## 1) Set environment variables

```bash
export SLACK_APP_NAME="slack-mirror-acme"
export SLACK_BOT_DISPLAY_NAME="slack-mirror"
export SLACK_REDIRECT_URL="https://localhost:3000/slack/oauth/callback"
# Optional if you use events:
export SLACK_EVENTS_URL="https://example.invalid/slack/events"
```

## 2) Render the manifest

```bash
python3 scripts/render_slack_manifest.py \
  --template manifests/slack-app.yaml \
  --output manifests/slack-app.rendered.yaml
```

## 3) Create app in target workspace

1. Go to `https://api.slack.com/apps`
2. Click **Create New App**
3. Choose **From an app manifest**
4. Select the target workspace
5. Paste contents of `manifests/slack-app.rendered.yaml`
6. Create app

## 4) Install + collect credentials

In the app settings:

1. **OAuth & Permissions** → Install app to workspace
2. Copy:
   - **Client ID**
   - **Client Secret**
   - Bot token (`xoxb-...`)
   - (Optional) user token (`xoxp-...`)

## 5) Put credentials in `config.yaml`

```yaml
workspaces:
  - name: workspace-a
    team_id: T01234567
    client_id: "123.456"
    client_secret: "..."
    token: "xoxb-..."
    user_token: "xoxp-..."
```

Repeat steps 1-5 for each workspace. Keep one manifest template; only credentials differ per workspace.
