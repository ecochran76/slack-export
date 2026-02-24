# Roadmap

## Current State

- Single-script exporter (`slack_export.py`)
- Point-in-time export of conversations, files, and canvases

## Target State

A multi-workspace Slack mirror platform with:

- Continuous sync (webhooks + reconciliation)
- Local structured database and cache
- Keyword + semantic search
- Service runtime
- MCP/OpenClaw skill readiness

## Delivery Phases

### Phase A — Foundations
- Modular project structure
- Config system (env interpolation + workspace scoping)
- SQLite schema/migrations with `workspace_id`
- CLI subcommand framework

### Phase B — Backfill + Cache
- Full backfill (users/channels/messages/files/canvases)
- Stable local cache layout
- Username↔ID map persistence/query APIs

### Phase C — Realtime
- Slack Events API ingestion
- Signature verification
- Event idempotency and replay-safe processing

### Phase D — Search & DX
- FTS5 keyword search
- Semantic indexing/retrieval pipeline
- Auto-generated CLI docs and shell completion

### Phase E — Platform Hardening
- Service packaging (systemd/docker)
- MCP endpoint/tool contracts
- OpenClaw skill packaging + runbook maturity
- Observability, retries, health checks

## Non-Goals (for initial rollout)

- Cross-platform GUI
- Full Slack administrative automation
- Perfect historical parity on restricted Slack plans
