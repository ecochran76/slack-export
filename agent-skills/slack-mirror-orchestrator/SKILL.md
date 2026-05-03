---
name: slack-mirror-orchestrator
description: Coordinate Slack Mirror work across ingest, live operations, search, and export workflows. Use when requests are broad or mixed (e.g., "set up syncing and verify indexing", "find results then export to PDF", "hydrate workspace then enable live mode"). Route to the most specific Slack Mirror sub-skill and preserve workspace/date/channel context across steps.
---

# Slack Mirror Orchestrator

Use this skill as the top-level router for Slack Mirror tasks.

## Route to sub-skills

- Use `slack-mirror-live-ops` for systemd/tmux services, dual-workspace live workers, queue/health checks.
- Use `slack-mirror-ingest` for backfill/hydration, auth-mode selection, file/canvas ingest, stalled runs.
- Use `slack-mirror-search` for keyword/semantic queries, direct Slack permalink/thread retrieval, relevance sanity checks, scoped retrieval.
- Use `slack-mirror-export` for channel/day exports, multi-day bundles, PDF formatting and attachments.
- Use `slack-mirror-send` for outbound Slack messages, DMs, and thread replies through MCP/API.
- Use `slack-mirror-channel-management` for channel create/reuse workflows and channel invitations through MCP/API.

## Orchestration rules

1. Keep workspace explicit in every command (`--workspace ...`).
2. Preserve prior context (workspace/channel/day/terms) unless user changes it.
3. Prefer deterministic checks after actions (service status, queue counts, query validation).
4. When search quality is noisy, run lexical cross-checks and report both.
5. If a run stalls, stop and pivot to bounded/safer pass rather than waiting indefinitely.
6. For real outbound writes, require clear workspace, target, sender mode, and message text; use idempotency keys.
7. For real channel-management writes, require clear workspace, channel name, privacy, and invitees.
8. If a request includes a Slack `/archives/<channel>/p<ts>` URL, route to `slack-mirror-search` and use permalink/thread retrieval before broad search or browser Slack.

## Minimal validation checklist

- Live ops change: verify webhooks + events + embeddings services are active.
- Ingest change: verify message/file/canvas counts moved as expected.
- Search change: verify keyword and semantic both return plausible hits.
- Direct permalink lookup: report workspace, channel id, selected timestamp, thread timestamp, mirrored status, and thread item count.
- Export change: produce output artifact path(s) and message count.
- Outbound send: report status, channel id, timestamp, and idempotent replay state.
- Channel management: report normalized channel name, channel id, created-vs-reused state, and invited user ids.
