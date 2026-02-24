# Runbook (Handoff + Operations)

This file is the continuity guide for future agents and contributors.

## Current Mission

Evolve this repo from one-time exporter to multi-workspace, continuously updated mirror platform.

## Working Conventions

- Planning/dev docs live in `docs/dev/`
- User-facing docs live in `docs/`
- Keep this runbook updated at each meaningful milestone
- Prefer small, coherent commits with explicit milestone labels

## Session Startup Checklist

1. Read:
   - `README.md`
   - `docs/ARCHITECTURE.md`
   - `docs/ROADMAP.md`
   - `docs/dev/PLAN.md`
   - `docs/dev/RUNBOOK.md`
2. Check repo status:
   - `git status --short --branch`
3. Confirm branch and open tasks before coding

## Milestone Log

### 2026-02-23 — Planning docs baseline

- Captured architecture, roadmap, engineering plan, and runbook
- Established docs split (`docs/` vs `docs/dev/`)

### 2026-02-23 — Phase A scaffolding (initial)

- Added `config.example.yaml` with env-var interpolation patterns
- Added `slack_mirror` package skeleton (`core`, `cli`, `search`, `service`, `integrations`)
- Added SQLite migration scaffold: `slack_mirror/core/migrations/0001_init.sql`
- Added config loader with `${ENV}` / `${ENV:-default}` support
- Added DB connector + migration applier
- Added CLI skeleton (`slack-mirror`) with stubs for:
  - `mirror init`
  - `workspaces list`
  - `channels sync-from-tool`
  - `docs generate`
  - `completion print bash|zsh`
- Added adapter for existing `~/.openclaw/workspace/scripts/slack_channels`

### 2026-02-23 — Phase A scaffolding (packaging + tests + workspace bootstrap)

- Added `pyproject.toml` with `slack-mirror` CLI entrypoint
- Added tests:
  - `tests/test_config.py`
  - `tests/test_db.py`
- Added workspace DB bootstrap commands:
  - `workspaces sync-config`
  - `workspaces list` now reads from DB
- Added DB helpers: `upsert_workspace`, `list_workspaces`

### 2026-02-23 — Phase B kickoff (API pagination + first backfill)

- Added Slack API client module: `slack_mirror/core/slack_api.py`
  - `auth_test`
  - cursor-paginated `users_list`
  - cursor-paginated `conversations_list`
- Added first backfill worker: `slack_mirror/sync/backfill.py`
  - backfills users + channels into DB
- Added DB upsert helpers:
  - `upsert_user`
  - `upsert_channel`
  - `get_workspace_by_name`
- Extended CLI:
  - `workspaces verify [--workspace <name>]`
  - `mirror backfill --workspace <name>`

### 2026-02-23 — Phase B (message history backfill + checkpoints)

- Added `conversations.history` pagination in `SlackApiClient`
- Added message backfill flow with per-channel checkpoints in `sync_state`
- Added DB helpers:
  - `upsert_message`
  - `list_channel_ids`
  - `set_sync_state` / `get_sync_state`
- Extended CLI `mirror backfill` with:
  - `--include-messages`
  - `--channel-limit`

### 2026-02-23 — Phase B (files/canvases metadata backfill)

- Checked the prior failed edit warning in `slack_mirror/core/slack_api.py` (it was a no-op edit attempt; file state is good)
- Added `files.list` pagination helper in Slack API client
- Added DB upserts:
  - `upsert_file`
  - `upsert_canvas`
- Added backfill flow for files/canvases metadata + deterministic local cache paths
- Extended CLI `mirror backfill` with:
  - `--include-files`
  - `--cache-root`

### 2026-02-23 — Phase B (file/canvas content downloads)

- Added downloader module with retries + SHA256 checksum:
  - `slack_mirror/sync/downloads.py`
- Added file DB update helper:
  - `update_file_download`
- Extended file/canvas backfill to optionally download content:
  - `--download-content`
- Verified with bot token:
  - `files_downloaded=15`, `canvases_downloaded=19`

### 2026-02-23 — Phase C kickoff (webhook service skeleton)

- Added HTTP webhook server skeleton:
  - `slack_mirror/service/server.py`
  - endpoint: `/slack/events`
  - health endpoint: `/healthz`
  - Slack signature verification + replay-window check
  - URL verification challenge support
- Added event-log DB helper:
  - `insert_event`
- Added CLI command:
  - `mirror serve-webhooks --workspace <name> [--bind] [--port]`
  - persists incoming events into `events` table with `pending` status

### 2026-02-23 — Phase C (event processor worker)

- Added event processor module:
  - `slack_mirror/service/processor.py`
  - consumes `events.status='pending'`
  - applies basic upserts for:
    - messages
    - channel_created/channel_rename
    - file_created/file_shared/file_change
  - marks events as `processed` or `error`
- Added CLI command:
  - `mirror process-events --workspace <name> [--limit N]`
- Added tests:
  - `tests/test_processor.py`

### 2026-02-23 — Phase C (expanded event coverage + loop mode)

- Expanded processor message handling:
  - supports `message_changed`
  - supports `message_deleted`
- Added processor loop mode:
  - `mirror process-events --loop --interval <seconds> [--max-cycles N]`

### 2026-02-24 — Phase C (channel membership events)

- Added DB migration:
  - `0002_channel_members.sql`
- Added DB helpers:
  - `upsert_channel_member`
  - `remove_channel_member`
- Expanded event processor coverage:
  - `member_joined_channel`
  - `member_left_channel`
- Added tests for channel membership writes and event handling

### 2026-02-24 — Phase B/C utility (message backfill time windows)

- Extended CLI `mirror backfill` with message window flags:
  - `--oldest`
  - `--latest`
- Extended backfill message path to pass bounds into `conversations.history`
- Preserved checkpoint behavior for default incremental mode only:
  - when no explicit `--oldest/--latest` is provided, checkpoint updates continue
  - when explicit bounds are provided, run is windowed and does not mutate channel checkpoint
- Updated CLI parsing tests and config docs examples

### 2026-02-24 — Phase B utility (smarter file type coverage)

- Extended files/canvases backfill with configurable file types:
  - new `mirror backfill --file-types <csv|all>` flag
  - default remains `images,snippets,gdocs,zips,pdfs`
  - `all` (or `*`) pulls all non-canvas file types
- Added canvas/file dedupe by file id when broad file fetch is used
- Updated CLI parsing tests and config docs examples

### 2026-02-24 — CLI UX (dynamic completion plumbing)

- Implemented `completion print bash|zsh` script emitters in CLI
- Added DB-backed/dynamic workspace completion:
  - completion scripts query `workspaces list --json` at completion time
- Added completion coverage for key backfill/event flags (including `--file-types`)
- Updated config docs with completion usage examples

## Next Actions Queue

1. Add docs generation command implementation (Markdown/man output)

## Decision Log Pointer

Use `docs/dev/DECISIONS.md` for ADR-style architectural decisions.

## Useful Commands

```bash
# quick sanity
python3 -m py_compile slack_export.py

# repo state
git status --short --branch
git log --oneline -n 10
```

## Handoff Template

When pausing, append:

- What changed
- What is pending
- Risks/blockers
- Recommended next command
