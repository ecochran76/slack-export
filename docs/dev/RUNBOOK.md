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

## Next Actions Queue

1. Add time-window controls (`--oldest`, `--latest`) for message backfill
2. Add smarter file type coverage beyond current list (or remove restrictive filter)
3. Add completion plumbing hooks for dynamic DB-backed values
4. Add docs generation command implementation (Markdown/man output)
5. Start realtime webhook ingestion skeleton (`service/server.py` + event log writes)

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
