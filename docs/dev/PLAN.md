# Development Plan (Engineering)

> Legacy planning context only.
> Canonical master plan: [`/home/ecochran76/workspace.local/slack-export/ROADMAP.md`](/home/ecochran76/workspace.local/slack-export/ROADMAP.md)
> Canonical dated turn log: [`/home/ecochran76/workspace.local/slack-export/RUNBOOK.md`](/home/ecochran76/workspace.local/slack-export/RUNBOOK.md)
> Canonical actionable plans: [`/home/ecochran76/workspace.local/slack-export/docs/dev/plans`](/home/ecochran76/workspace.local/slack-export/docs/dev/plans)
> Do not use this file for new active planning.

## Scope Summary

Re-architect `slack_export` into a modular, multi-workspace mirror system with realtime updates, local indexing/search, service operation, and ecosystem integrations.

## Requirements Collected

1. Multi-workspace support
2. Config files with env var interpolation for secrets
3. Automatic CLI docs generation
4. Smart bash/zsh autocompletion (including DB-resolved values)
5. MCP-ready interface
6. OpenClaw-skill / Codex friendly UX
7. Runnable as long-lived service
8. Full local cache including files/canvases + username-ID map
9. Keyword + semantic search
10. Integration with `~/.openclaw/workspace/scripts/slack_channels`

## Proposed Package Layout

```text
slack_export/
  cli/
  core/
    config.py
    db.py
    models.py
    migrations/
  sync/
    backfill.py
    reconcile.py
    events.py
    files.py
    canvases.py
  search/
    keyword.py
    semantic.py
  integrations/
    slack_channels.py
    mcp.py
  service/
    server.py
    workers.py
docs/
  ARCHITECTURE.md
  ROADMAP.md
  dev/
```

## Data Model (v1)

- `workspaces(id, name, team_id, domain, config_json, created_at, updated_at)`
- `users(workspace_id, user_id, username, display_name, real_name, email, is_bot, raw_json, updated_at)`
- `channels(workspace_id, channel_id, name, is_private, is_im, is_mpim, topic, purpose, raw_json, updated_at)`
- `messages(workspace_id, channel_id, ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json, updated_at)`
- `files(workspace_id, file_id, name, title, mimetype, size, local_path, checksum, raw_json, updated_at)`
- `canvases(workspace_id, canvas_id, title, local_path, raw_json, updated_at)`
- `events(workspace_id, event_id, event_ts, type, status, payload_json, error, processed_at)`
- `sync_state(workspace_id, key, value, updated_at)`
- `content_chunks(workspace_id, source_type, source_id, chunk_index, text, token_count, created_at)`
- `embeddings(workspace_id, chunk_ref, model, vector_blob, created_at)`

## Config Spec (draft)

```yaml
version: 1
storage:
  db_path: ${SLACK_MIRROR_DB:-./data/slack_mirror.db}
  cache_root: ${SLACK_MIRROR_CACHE:-./cache}
workspaces:
  - name: acme
    team_id: T123
    token: ${SLACK_ACME_TOKEN}
    signing_secret: ${SLACK_ACME_SIGNING_SECRET}
    enabled: true

service:
  bind: ${SLACK_MIRROR_BIND:-127.0.0.1}
  port: ${SLACK_MIRROR_PORT:-8787}

search:
  embeddings_model: ${SLACK_MIRROR_EMBED_MODEL:-text-embedding-3-large}
```

## CLI Direction

- Keep legacy behavior under `backup`
- New command groups:
  - `mirror init|backfill|reconcile|serve|status`
  - `search keyword|semantic`
  - `workspaces list|add|verify`
  - `channels sync-from-tool|resolve|list`
  - `docs generate`
  - `completion bash|zsh`

## Integration: `slack_channels`

- Adapter wraps shell script and parses stdout/errors
- Primary use: resolve/fetch/create/invite channels
- Optional import sync from its JSON store into local DB

## Acceptance Criteria (Phase A)

- Config parser supports env interpolation with defaults
- DB schema includes `workspace_id` across core entities
- New CLI skeleton compiles/tests pass
- Planning docs + runbook committed
