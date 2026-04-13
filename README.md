# Slack Exporter

A Python script to export Slack conversations, canvases, and files.

This repo also contains the newer `slack_mirror` package for multi-workspace ingest, local search, and always-on live sync. For current live-ops setup, use the runbooks in [docs/dev/LIVE_MODE.md](/home/ecochran76/workspace.local/slack-export/docs/dev/LIVE_MODE.md) and [docs/CLI.md](/home/ecochran76/workspace.local/slack-export/docs/CLI.md).
For the shipped local API and MCP response semantics, including outbound writes and listener deliveries, see [docs/API_MCP_CONTRACT.md](/home/ecochran76/workspace.local/slack-export/docs/API_MCP_CONTRACT.md).

## Current Live Topology

For unattended live operation, the supported systemd user-service topology is:

- one `serve-socket-mode` unit per workspace
- one unified `daemon` unit per workspace

Do not run the older split `process-events` and `process-embedding-jobs` units alongside the unified daemon for the same workspace. That creates duplicate writers against the same SQLite DB and can lead to lock contention.

Useful commands:

```bash
scripts/install_live_mode_systemd_user.sh default
scripts/install_live_mode_systemd_user.sh soylei
scripts/live_mode_status_all.sh
slack-mirror user-env validate-live
slack-mirror user-env validate-live --json
slack-mirror --config ~/.config/slack-mirror/config.yaml mirror status --workspace default --healthy --enforce-stale
slack-mirror user-env check-live
slack-mirror user-env check-live --json
slack-mirror user-env status --json
slack-mirror user-env snapshot-report
slack-mirror user-env snapshot-report --name morning-ops --json
python scripts/render_runtime_report.py --base-url http://slack.localhost --format markdown --output /tmp/slack-mirror-runtime-report.md
python scripts/render_runtime_report.py --base-url http://slack.localhost --format html --output /tmp/slack-mirror-runtime-report.html
slack-mirror user-env recover-live
slack-mirror user-env recover-live --apply
slack-mirror user-env rollback
slack-mirror mirror process-derived-text-jobs --workspace default
slack-mirror mirror process-derived-text-jobs --workspace default --kind ocr_text
slack-mirror mirror reconcile-files --workspace default --auth-mode user --limit 100
slack-mirror mirror reconcile-files --workspace default --auth-mode user --limit 100 --json
python scripts/export_channel_day_docx.py --input-json exports/day.json --output-docx exports/day.docx
python scripts/export_channel_day_docx.py --input-json exports/day.json --output-docx exports/day.docx --font-family Aptos --font-size-pt 11 --margin-in 1.25 --compactness cozy --accent-color 8B5CF6
python scripts/export_multi_day_docx.py --inputs exports/*.json --output-docx exports/daypack.docx
python scripts/render_export_docx_fixtures.py --output-dir exports/docx-fixtures
python scripts/validate_export_docx.py --input-docx exports/day.docx --json --fail-on-issues
PYTHONPATH=. ./.venv/bin/python scripts/export_channel_day.py --config ~/.config/slack-mirror/config.yaml --db ~/.local/state/slack-mirror/slack_mirror.db --workspace default --channel general --day 2026-04-12 --managed-export --link-audience local
slack-mirror api serve
slack-mirror search derived-text --workspace default --query "incident review"
slack-mirror search derived-text --workspace default --query "invoice total" --kind ocr_text
slack-mirror search corpus --workspace default --query "incident review" --mode hybrid
slack-mirror search corpus --all-workspaces --query "incident review" --mode hybrid
slack-mirror search health --workspace default
slack-mirror search health --workspace default --dataset ./docs/dev/benchmarks/slack_corpus_smoke.jsonl
slack-mirror search health --workspace default --dataset ./docs/dev/benchmarks/slack_corpus_depth.jsonl
slack-mirror release check
slack-mirror release check --require-clean --require-release-version
./.venv/bin/python -m unittest discover -s tests -v
```

## Search Direction

The current repo has:

- keyword, semantic, and hybrid message search
- first-class derived-text storage for files and canvases
- a queued attachment-text extraction path for canvases, UTF-8 text-like files, OOXML and OpenDocument office files (`.docx`, `.pptx`, `.xlsx`, `.odt`, `.odp`, `.ods`), with `.docx` extraction now including visible text from document, header, footer, footnote, and endnote story parts, `.pptx` extraction now using visible slide text, `.xlsx` extraction now resolving shared strings, inline strings, and numeric cell values, and machine-readable PDFs when `pdftotext` is available
- an OCR-derived text path for image-like files and scanned PDFs when `tesseract` and `pdftoppm` are available
- a shared extraction-provider boundary that keeps the current host-local toolchain as the default path and now supports optional command-backed and HTTP-backed providers selected from config, with local extraction retained as the fallback path by default
- a corpus-wide hybrid search path over messages plus derived text through `search corpus`
- an explicit cross-workspace corpus-search path through `search corpus --all-workspaces`
- chunk-aware derived-text retrieval so long attachments and OCR-heavy documents surface the matching segment instead of only the top-level document row
- a machine-readable search health path over readiness plus optional smoke benchmarks through `search health`
- a bounded DOCX-grade export follow-up lane, with channel/day JSON as the canonical artifact for future DOCX rendering
- the shipped DOCX baseline now includes:
  - explicit paragraph styles over the same channel/day JSON artifact
  - compact 1in-margin, sans-serif 10pt defaults
  - subtle paragraph shading for top-level and reply message blocks
  - reply indentation without internal thread-ID noise
  - tighter sender metadata alignment
  - attachment link/source blocks with compact type badges and human-readable type labels
  - safer link preference for public URLs/permalinks over brittle local filesystem links
  - config-backed managed export bundles with deterministic export IDs and reverse-proxied `/exports/<export-id>/<filepath>` download URLs
  - shared portable attachment links across HTML, PDF, and DOCX through emitted `public_url` / `download_url` fields, plus audience-keyed `download_urls` / `preview_urls`
  - API-served export manifests through `/v1/exports` and `/v1/exports/<export-id>` so the live service owns the configured bundle URL contract
  - bundle HTML reports published directly at `/exports/<export-id>`
  - channel/day HTML reports now render message bubbles and sender avatars when profile imagery is available, group consecutive same-sender messages, use participant-aware DM titles instead of raw workspace/channel ids, show tenant/channel/thread identifiers in code-style metadata, keep attachment metadata compact instead of printing full raw URLs, materialize Slack-native email previews into managed bundles when no local binary exists, opportunistically download hosted Slack attachments into the managed bundle when a file row exists but the mirror has not yet persisted a local binary, and preserve repaired local email HTML artifacts with companion inline-asset directories when those artifacts are published, while rejecting Slack HTML/login interstitials instead of publishing them as fake local files
  - `mirror reconcile-files` now reports separate counts for repaired ordinary binaries versus repaired Slack-for-Gmail email containers, so operators can tell what kind of recovery actually occurred
  - `mirror reconcile-files` also reports partial email-container localization warnings when the HTML body is repaired but some inline assets remain missing
  - `mirror reconcile-files` now emits per-reason remediation hints in both plain output and `--json`
  - `mirror reconcile-files` now persists the last run outcome in local state and compares the current batch to the previous run in both plain output and `--json`, so operators can spot regressions instead of reading each batch in isolation
  - `user-env validate-live` and `user-env check-live` now surface the latest persisted reconcile-files evidence per workspace, and warn when the most recent repair batch recorded warnings or failures
  - lightweight managed-runtime status is now queryable over CLI, API (`/v1/runtime/status`), and MCP (`runtime.status`), including the latest persisted reconcile summary per workspace
  - `scripts/render_runtime_report.py` now consumes `/v1/runtime/status` and `/v1/runtime/live-validation` to generate shareable Markdown or HTML runtime snapshots for ops review
  - `user-env snapshot-report` now writes Markdown and HTML runtime snapshots into the managed state directory under `runtime-reports/`, alongside stable `*.latest.*` copies for review or handoff, while pruning older timestamped snapshots with a bounded retention policy
  - the local API now publishes the latest managed runtime snapshots through `/v1/runtime/reports`, `/v1/runtime/reports/<name>`, `/v1/runtime/reports/latest`, a browser index at `/runtime/reports`, and direct HTML at `/runtime/reports/<name>` or `/runtime/reports/latest`, with the freshest snapshot highlighted on the index and header links for the latest HTML and manifest
  - MCP now exposes the freshest managed runtime snapshot manifest through `runtime.report.latest`
  - the local API now supports a bounded local-password browser-auth baseline for `/runtime/reports*` and `/exports*`, with login/register HTML pages and cookie-backed sessions modeled on the lighter parts of the `../litscout` hosted auth seam
  - frontend auth cookie policy is now request-aware, so browser-origin HTTPS ingress can use `Secure` cookies without breaking the local `http://slack.localhost` path
  - the managed user-env install now also provisions `slack-mirror-runtime-report.timer`, which runs `user-env snapshot-report` hourly into the same managed state directory
  - bounded browser preview support for images, PDFs, and text-like files through `/exports/<export-id>/<filepath>/preview`
  - lightweight `.docx` browser preview through `mammoth`, without requiring a full office server
  - lightweight `.pptx` and `.xlsx` browser previews through the repo's OOXML extraction layer, without requiring a full office server
  - lightweight OpenDocument browser previews for `.odt`, `.odp`, and `.ods` through the repo's extraction layer, without requiring a full office server
  - render-engine-compatible OOXML output that can be visually QA'd through the `docx-skill` render path
  - bounded appearance controls for font family, body size, margins, compactness, and accent color
  - a one-command fixture-artifact generator for canonical DOCX/PDF/PNG visual review outputs

The active search modernization lane is [0006-2026-04-11-search-evaluation-modernization.md](/home/ecochran76/workspace.local/slack-export/docs/dev/plans/0006-2026-04-11-search-evaluation-modernization.md). The derived-text ownership contract for this first slice is in [DERIVED_TEXT_CONTRACT.md](/home/ecochran76/workspace.local/slack-export/docs/dev/DERIVED_TEXT_CONTRACT.md).

## Description

The `slack_export.py` script uses a Slack user token to export:

- Public Channels
- Private Channels
- Direct Messages (1:1 DMs)
- Multi-Person Messages (Group DMs)
- Canvases
- Files

This script retrieves all conversations your user participates in, downloads their complete message history, and saves each as separate JSON files. It also exports canvases and files you have access to into dedicated directories. Unlike Slack's official exporter, which only covers public channels, this tool provides a user-centric export, including private content you can see.

**Note**: Export capabilities may be limited by your Slack workspace’s plan (e.g., free plans restrict some historical data) or your user’s permissions.

Slack endorses this API usage for personal exports (see [Slack's API documentation](https://get.slack.help/hc/en-us/articles/204897248)):  
*"If you want to export the contents of your own private groups and direct messages, please see our API documentation."*

### Getting a Slack Token

To use this script, you need a Slack **user token** (starts with `xoxp-`). Legacy tokens are deprecated, so follow these steps to create a Slack app and obtain a user token:

1. **Create a Slack App**:
   - Go to [api.slack.com/apps](https://api.slack.com/apps) and click "Create New App".
   - Name it (e.g., "Slack Exporter") and select your workspace.

2. **Configure Permissions**:
   - Navigate to "OAuth & Permissions".
   - Under "User Token Scopes", add:
     - `channels:history` (public channel messages)
     - `groups:history` (private channel messages)
     - `im:history` (1:1 DMs)
     - `mpim:history` (group DMs)
     - `files:read` (files and canvases)
     - `users:read` (user info for names/IDs)
   - These scopes enable the script to access your conversations, files, and canvases.

3. **Install the App**:
   - Go to "Install App" and click "Install to Workspace".
   - Authorize as yourself (e.g., `ecochran76`).
   - Copy the **User OAuth Token** (`xoxp-...`) from "OAuth & Permissions".

4. **Use the Token**:
   - Pass it to the script with the `--token` argument.

#### Bot vs. User Tokens
- **User Tokens (`xoxp-`)**:
  - Act as you (e.g., `ecochran76`), exporting data you can see in Slack.
  - Include private channels, DMs, and files/canvases you have access to, based on your permissions.
  - **Required** for this script to export your full personal data.

- **Bot Tokens (`xoxb-`)**:
  - Represent a bot user tied to the app, not your account.
  - Limited to public channels and bot interactions unless invited to private conversations.
  - **Not suitable** here—using a bot token will omit private channels, DMs, and most user-specific files/canvases.

Ensure you use a user token (`xoxp-`) for complete exports.

---

## Credits

This project is a fork of [zach-snell/slack-export](https://github.com/zach-snell/slack-export). Many thanks to Zach Snell for the original implementation, which inspired and formed the basis for this enhanced version.

---

## Dependencies

Install the required Python packages:

```bash
pip install slack_sdk  # https://github.com/slackapi/python-slack-sdk
pip install pick       # https://github.com/wong2/pick
pip install requests   # For downloading files and canvases
```

---

## Usage

The script exports all conversations (public channels, private channels, group DMs, 1:1 DMs), canvases, and files your user can access by default, saving them to a directory named `<timestamp>-slack_export` (e.g., `20250303-172345-slack_export`). Use the flags below to customize the export process, filter conversations, or modify output behavior.

### Command-Line Flags

- **`--token TOKEN`**  
  - **Required**: The Slack user token (`xoxp-...`) obtained from your Slack app.
  - Example: `--token xoxp-123...`

- **`--zip ZIP_NAME`**  
  - Optional: Creates a zip archive of the export directory (e.g., `slack_export.zip`) and deletes the original folder after zipping.
  - Useful for compatibility with tools like `slack-export-viewer`.
  - Default: No zip file is created.
  - Example: `--zip my_export`

- **`-o, --output PATH`**  
  - Optional: Specifies the base directory where the export folder (`<timestamp>-slack_export`) is created.
  - Supports `~` for your home directory (e.g., `~/slack_backups` on Windows becomes `C:\Users\YourUsername\slack_backups`).
  - Default: Current working directory.
  - Example: `-o ~/slack_backups`

- **`--dryRun`**  
  - Optional: Lists all available conversations (public channels, private channels, group DMs, 1:1 DMs) your user can export without fetching or saving anything.
  - Useful for previewing what will be exported.
  - Default: Disabled (full export runs).
  - Example: `--dryRun`

- **`--publicChannels [CHANNEL_NAME ...]`**  
  - Optional: Exports public channels. Without names, exports all public channels you’re in; with names, filters to the specified channels.
  - Names are case-sensitive and must match exactly (e.g., `General`, not `general`).
  - Default: Exports all public channels unless filtered.
  - Example: `--publicChannels General Random`

- **`--groups [GROUP_NAME ...]`**  
  - Optional: Exports private channels and group DMs. Without names, exports all you’re in; with names, filters to the specified ones.
  - Names must match exactly (e.g., `my_private_channel` or `mpdm-user1--user2-1`).
  - Default: Exports all private channels and group DMs unless filtered.
  - Example: `--groups my_private_channel`

- **`--directMessages [USER_NAME ...]`**  
  - Optional: Exports 1:1 DMs. Without names, exports all your DMs; with names, filters to the specified users.
  - Uses Slack usernames (e.g., `jane_smith`), not display names.
  - Default: Exports all 1:1 DMs unless filtered.
  - Example: `--directMessages jane_smith john_doe`

- **`--prompt`**  
  - Optional: Opens an interactive menu to select conversations (public channels, private channels/group DMs, 1:1 DMs) to export.
  - If combined with `--publicChannels`, `--groups`, or `--directMessages` with names, those named items are exported automatically, and the prompt applies to the unspecified types.
  - Default: Disabled (exports all conversations unless filtered).
  - Example: `--prompt`

### Usage Examples

```bash
# Export everything (channels, DMs, canvases, files) to the current directory
python slack_export.py --token xoxp-123...

# Export everything and save to a custom directory
python slack_export.py --token xoxp-123... -o ~/slack_backups

# Export everything into a zip file
python slack_export.py --token xoxp-123... --zip slack_export

# Preview all exportable conversations without saving
python slack_export.py --token xoxp-123... --dryRun

# Export only specific public channels
python slack_export.py --token xoxp-123... --publicChannels General Random

# Export all private channels and group DMs to a custom directory
python slack_export.py --token xoxp-123... --groups -o ~/backups

# Export 1:1 DMs with specific users
python slack_export.py --token xoxp-123... --directMessages jane_smith john_doe

# Export all public channels and specific group DMs
python slack_export.py --token xoxp-123... --publicChannels --groups mpdm-user1--user2-1

# Export DMs with jane_smith and prompt for public channels
python slack_export.py --token xoxp-123... --directMessages jane_smith --publicChannels --prompt

# Prompt for all conversation types interactively
python slack_export.py --token xoxp-123... --prompt

# Export public/private channels (no DMs) into a zip file
python slack_export.py --token xoxp-123... --publicChannels --groups --zip channels_only
```

### Notes on Behavior
- **Default Behavior**: Without filtering flags (`--publicChannels`, `--groups`, `--directMessages`), all conversations, canvases, and files are exported unless `--prompt` is used to select manually.
- **Combining Flags**: Use multiple flags to export specific subsets (e.g., `--publicChannels --directMessages` skips private channels/group DMs).
- **Canvases and Files**: Always exported unless `--dryRun` is used, regardless of conversation filters.
- **Rate Limits**: The script includes `sleep(1)` between API calls to respect Slack’s rate limits, which may slow large exports.

---

## Credits

This project is a fork of [zach-snell/slack-export](https://github.com/zach-snell/slack-export). Many thanks to Zach Snell for the original implementation, which inspired and formed the basis for this enhanced version.

---

## Dependencies

Install the required Python packages:

```bash
pip install slack_sdk  # https://github.com/slackapi/python-slack-sdk
pip install pick       # https://github.com/wong2/pick
pip install requests   # For downloading files and canvases
```

---

## Output Structure

- `users.json`: List of workspace users.
- `channels.json`: Metadata for exported conversations.
- `<channel_name>/<date>.json`: Message history for each channel/DM, split by date.
- `canvases/canvases.json`: Metadata for exported canvases.
- `canvases/<canvas_title>_<id>.html`: Exported canvas files.
- `files/files.json`: Metadata for exported files.
- `files/<file_name>`: Exported files (e.g., PDFs, images).

---

## Recommended Tools

Pairs with `slack-export-viewer` for viewing exports:

```bash
pip install slack-export-viewer
slack-export-viewer -z slack_export.zip
```

---

## Limitations

- Requires a user token (`xoxp-`) with scopes like `channels:history`, `files:read`, etc.
- Exports are limited to what your user can access in Slack.
- Free Slack plans may restrict message history or file access.

---

## License

This script is provided as-is, with no guarantees of updates or support. See the original repository for licensing details: [zach-snell/slack-export](https://github.com/zach-snell/slack-export).
