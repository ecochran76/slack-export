# Daily Briefing / Slack Mirror Hardening Plan

## Problem

We saw false-empty Slack briefings because runtime resolution depended on the process cwd:

- config selection was implicit and cwd-sensitive
- `storage.db_path` could be relative to the cwd instead of the config location
- repo-local DBs were easy to accidentally use in automation
- a stale or wrong DB could produce `0` results that looked real

## Decision

Separate **user-scope runtime** from **repo-local dev/test**.

### User-scope runtime (recommended)

- Config: `~/.config/slack-mirror/config.yaml`
- DB: `~/.local/state/slack-mirror/slack_mirror.db`
- Cache: `~/.local/cache/slack-mirror`

### Repo-local dev/test

- Config: `config.local.yaml`
- DB: `./.local/state/slack_mirror_test.db`
- Cache: `./.local/cache`

## Implemented in this change set (P0)

1. **Config discovery for human CLI use**
   - If `--config` is omitted, search:
     1. `./config.local.yaml`
     2. `./config.yaml`
     3. `~/.config/slack-mirror/config.yaml`
   - Automation should still pass an explicit `--config`.

2. **Path normalization relative to config file**
   - `dotenv`
   - `storage.db_path`
   - `storage.cache_root`
   
   These now resolve relative to the config file directory instead of the cwd.

3. **Stable user-scope defaults**
   - `config.example.yaml` now defaults to user-scope state/cache locations.

4. **User install/update migration**
   - `scripts/user_env.sh` now uses:
     - `~/.local/state/slack-mirror`
     - `~/.local/cache/slack-mirror`
   - legacy state under `~/.local/share/slack-mirror/var` is migrated forward when possible.

5. **Docs updates**
   - config resolution and path rules documented
   - repo-local test DB docs clarified as dev/test only
   - user install docs updated to stable runtime locations

## Next recommended change set (P1)

1. **Stop using `search keyword` as message retrieval**
   - Search is ranked and capped, so it is the wrong primitive for exact briefing windows.
   - Replace with a direct windowed message listing primitive.

2. **Switch the daily briefing from previous-day slices to a rolling last-24h window**
   - `after = now - 24h`
   - `before = now`

3. **Fail loudly on stale or wrong sources**
   - missing config
   - missing DB
   - stale mirror max timestamp
   - workspace missing from DB

## Acceptance criteria

- same Slack result regardless of cwd
- repo-local test DB no longer masquerades as stable runtime storage
- user install survives repo moves/branch changes
- config-relative paths remain stable even when launched from cron/systemd/OpenClaw
