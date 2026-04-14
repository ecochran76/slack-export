# Configuration (Preview)

`slack-mirror` uses YAML configuration with environment variable interpolation.

## Example

Copy `config.example.yaml` to `~/.config/slack-mirror/config.yaml` for a stable user-scope install, or to `config.local.yaml` in the repo for local dev/test.

```yaml
version: 1
storage:
  db_path: ${SLACK_MIRROR_DB:-~/.local/state/slack-mirror/slack_mirror.db}
  cache_root: ${SLACK_MIRROR_CACHE:-~/.local/cache/slack-mirror}
service:
  bind: ${SLACK_MIRROR_BIND:-127.0.0.1}
  port: ${SLACK_MIRROR_PORT:-8787}
  auth:
    enabled: ${SLACK_MIRROR_AUTH_ENABLED:-false}
    allow_registration: ${SLACK_MIRROR_AUTH_ALLOW_REGISTRATION:-false}
    registration_allowlist: ${SLACK_MIRROR_AUTH_REGISTRATION_ALLOWLIST:-}
    cookie_name: ${SLACK_MIRROR_AUTH_COOKIE_NAME:-slack_mirror_hosted_session}
    cookie_secure_mode: ${SLACK_MIRROR_AUTH_COOKIE_SECURE_MODE:-auto}
    session_days: ${SLACK_MIRROR_AUTH_SESSION_DAYS:-30}
    session_idle_timeout_seconds: ${SLACK_MIRROR_AUTH_SESSION_IDLE_TIMEOUT_SECONDS:-43200}
    login_attempt_window_seconds: ${SLACK_MIRROR_AUTH_LOGIN_WINDOW_SECONDS:-900}
    login_attempt_max_failures: ${SLACK_MIRROR_AUTH_LOGIN_MAX_FAILURES:-5}
exports:
  root_dir: ${SLACK_MIRROR_EXPORT_ROOT:-~/.local/share/slack-mirror/exports}
  local_base_url: ${SLACK_MIRROR_EXPORT_LOCAL_BASE_URL:-http://slack.localhost}
  external_base_url: ${SLACK_MIRROR_EXPORT_EXTERNAL_BASE_URL:-https://slack.ecochran.dyndns.org}

workspaces:
  - name: default
    team_id: ${SLACK_TEAM_ID:-}
    token: ${SLACK_TOKEN:-}
    outbound_token: ${SLACK_WRITE_BOT_TOKEN:-}
    user_token: ${SLACK_USER_TOKEN:-}
    outbound_user_token: ${SLACK_WRITE_USER_TOKEN:-}
    signing_secret: ${SLACK_SIGNING_SECRET:-}
    enabled: true
```

## Interpolation syntax

- `${VAR}` → required env var (empty if not set)
- `${VAR:-fallback}` → env var with default fallback

## Token selection by action

- `token` / `user_token` are the default read-path credentials.
- `outbound_token` / `outbound_user_token` are used for write actions such as sending messages or thread replies.
- If outbound token fields are not set, the service falls back to workspace-aware env aliases for writes.
- For the `default` workspace, generic env names like `SLACK_BOT_TOKEN` and `SLACK_USER_TOKEN` are considered write-capable fallbacks.
- For production installs, prefer explicit outbound fields rather than fallback heuristics.
- `workspaces verify --require-explicit-outbound` enforces that policy during validation.

## Path resolution rules

- `dotenv`, `storage.db_path`, and `storage.cache_root` are resolved relative to the **config file directory**, not the process cwd.
- `~` is expanded for user-scope paths.
- If `--config` is omitted, the CLI searches in this order:
  1. `./config.local.yaml`
  2. `./config.yaml`
  3. `~/.config/slack-mirror/config.yaml`

For automation, prefer passing an explicit `--config` path anyway.

## Service and export settings

- `service.bind` and `service.port` are the canonical local API listen settings.
- `slack-mirror api serve` now defaults to those config values when `--bind` or `--port` are omitted.
- `service.auth.enabled` turns on the local browser-auth baseline for published runtime-report and export surfaces.
- `service.auth.allow_registration` controls whether new local frontend users can self-register through `/register`. The shipped config template now defaults this to `false` for a stricter live posture.
- `service.auth.registration_allowlist` optionally restricts self-registration to specific normalized usernames, including email-style usernames such as `ecochran76@gmail.com`.
- `service.auth.cookie_name`, `service.auth.cookie_secure_mode`, and `service.auth.session_days` control the browser session cookie contract.
- `service.auth.session_idle_timeout_seconds` controls inactivity expiry for browser sessions based on `last_seen_at`.
- `service.auth.login_attempt_window_seconds` and `service.auth.login_attempt_max_failures` control the bounded failed-login throttle for `/auth/login`.
- `service.auth.cookie_secure_mode` accepts:
  - `auto` — mark cookies `Secure` only for HTTPS requests
  - `always` — always mark cookies `Secure`
  - `never` — never mark cookies `Secure`
- in `auto`, the service first trusts browser origin/referrer scheme, then reverse-proxy proto headers, and finally falls back to the configured local/external base-host mapping when deciding whether a request is HTTPS-backed.
- the older `service.auth.cookie_secure` boolean is still accepted as a compatibility override, but `cookie_secure_mode` is the canonical setting.
- when frontend auth is enabled, browser auth POST routes (`/auth/register`, `/auth/login`, `/auth/logout`) are same-origin only and require a matching `Origin` or `Referer` header.
- when the failed-login threshold is exceeded inside the configured window, `/auth/login` returns `429 RATE_LIMITED` with retry metadata instead of a generic invalid-credential response.
- when a browser session exceeds the configured inactivity timeout, the shared auth resolver revokes it and treats it as unauthenticated on the next request.
- per-user browser session inspection and revocation are available through `/auth/sessions` and `/auth/sessions/<id>/revoke`.
- when frontend auth is enabled, protected HTML routes redirect unauthenticated browsers to `/login`, while protected JSON routes fail with `AUTH_REQUIRED`.
- `exports.root_dir` is the user-scoped bundle root for managed export artifacts.
- `exports.local_base_url` is the preferred base URL for local reverse-proxied download links, intended for `http://slack.localhost`.
- `exports.external_base_url` is the preferred base URL for externally published download links, intended for `https://slack.ecochran.dyndns.org`.
- managed exports now emit both local and external URL maps when both base URLs are configured, so consumers can switch audiences without rerunning the export.
- the API export manifest endpoints rebuild bundle URLs from current config, so the live service remains the canonical owner of the published HTTP/HTTPS export contract.

Managed export URLs use this path contract:

- `/exports/<export-id>` serves the bundle HTML report
- `/exports/<export-id>/<filepath>`
- `/exports/<export-id>/<filepath>/preview`
- `/v1/exports`
- `/v1/exports/<export-id>`
- `/auth/status`
- `/auth/session`
- `/auth/sessions`
- `/auth/register`
- `/auth/login`
- `/auth/logout`
- `/login`
- `/register`

Current preview support behind the local API:
- images: inline preview
- PDFs: iframe preview
- `.docx`: HTML preview through `mammoth`
- `.pptx`: slide-by-slide HTML summary through the repo's OOXML extraction path
- `.xlsx`: sheet-table HTML summary through the repo's OOXML extraction path
- `.odt`: HTML text summary through the repo's OpenDocument extraction path
- `.odp`: slide-by-slide HTML summary through the repo's OpenDocument extraction path
- `.ods`: sheet-table HTML summary through the repo's OpenDocument extraction path
- text-like files (`text/*`, JSON, XML): escaped text preview
- other content types: `PREVIEW_UNSUPPORTED`

`<export-id>` is deterministic, URL-friendly, and human-readable. The current format is a bounded readable slug with a short stable hash suffix, for example:

- `channel-day-default-general-2026-04-12-a1b2c3d4e5`

## Commands (scaffold)

```bash
python -m slack_mirror.cli.main --config config.yaml mirror init
python -m slack_mirror.cli.main --config config.yaml workspaces sync-config
python -m slack_mirror.cli.main --config config.yaml workspaces verify
python -m slack_mirror.cli.main --config config.yaml workspaces verify --require-explicit-outbound
python -m slack_mirror.cli.main --config config.yaml workspaces list
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-messages --channel-limit 5
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-messages --oldest 1700000000.000000 --latest 1800000000.000000
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-files --cache-root ./cache
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-files --file-types all --cache-root ./cache
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-files --download-content --cache-root ./cache
python -m slack_mirror.cli.main channels sync-from-tool
python -m slack_mirror.cli.main search reindex-keyword --workspace default
python -m slack_mirror.cli.main search keyword --workspace default --query deploy --limit 20
python -m slack_mirror.cli.main search keyword --workspace default --query "deploy from:<@U123> channel:<#C123> has:link -draft after:1700000000"
python -m slack_mirror.cli.main docs generate --format markdown --output docs/CLI.md
python -m slack_mirror.cli.main docs generate --format man --output docs/slack-mirror.1
python scripts/check_generated_docs.py

# after install (entrypoint)
slack-mirror --config config.yaml mirror init

# webhook service
python -m slack_mirror.cli.main --config config.yaml mirror serve-webhooks --workspace default --bind 127.0.0.1 --port 8787
python -m slack_mirror.cli.main --config config.yaml mirror process-events --workspace default --limit 200
python -m slack_mirror.cli.main --config config.yaml mirror process-events --workspace default --loop --interval 2 --max-cycles 10

# shell completion scripts
python -m slack_mirror.cli.main completion print bash > /tmp/slack-mirror.bash
python -m slack_mirror.cli.main completion print zsh > /tmp/_slack-mirror
```

> Note: This is scaffold-level documentation during Phase A. Behavior and command names may evolve.
