# Slack Mirror Architecture (User-Facing)

This project is evolving from a one-time Slack export script into a continuous, local-first workspace mirror.

## Goals

- Mirror one or more Slack workspaces locally
- Keep data fresh via Events API (webhooks) + scheduled reconciliation
- Cache messages, files, and canvases with stable local paths
- Provide both keyword and semantic search
- Run as a CLI and long-running service

## Core Components

1. **CLI**
   - Backup/export commands
   - Mirror initialization and sync commands
   - Search commands

2. **Sync Engine**
   - Initial backfill from Slack Web API
   - Incremental sync from webhook events
   - Reconciliation jobs for missed events/rate-limit gaps

3. **Local Data Layer**
   - SQLite primary database (multi-workspace)
   - FTS5 indexes for keyword search
   - Embedding storage/index for semantic search

4. **Content Cache**
   - Files and canvases downloaded to deterministic cache paths
   - Metadata and checksums tracked in DB

5. **Service Runtime**
   - Webhook listener
   - Worker queues / processors
   - Health checks and structured logs

## Multi-Workspace Model

All primary entities are keyed by `workspace_id` in addition to Slack IDs:

- users
- channels
- messages
- files
- canvases
- events
- sync checkpoints

This enables one local mirror instance to track many workspaces cleanly.

## Security and Secrets

Configuration supports environment-variable interpolation (for tokens and signing secrets), with optional file-based or command-based secret providers.

## Integrations

- Existing channel tool: `~/.openclaw/workspace/scripts/slack_channels`
- MCP-compatible API surface planned
- OpenClaw-skill and Codex-friendly non-interactive CLI modes (`--json`)

## Planned UX

- Generated CLI docs and shell completions (bash/zsh)
- Dynamic completion for DB-backed items (workspace names, channel names, users)

For implementation details and active planning status, see `docs/dev/`.
