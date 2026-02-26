---
name: slack-mirror-orchestrator
description: Coordinate Slack Mirror work across ingest, live operations, search, and export workflows. Use when requests are broad or mixed (e.g., "set up syncing and verify indexing", "find results then export to PDF", "hydrate workspace then enable live mode"). Route to the most specific Slack Mirror sub-skill and preserve workspace/date/channel context across steps.
---

# Slack Mirror Orchestrator

Use this skill as the top-level router for Slack Mirror tasks.

## Route to sub-skills

- Use `slack-mirror-live-ops` for systemd/tmux services, dual-workspace live workers, queue/health checks.
- Use `slack-mirror-ingest` for backfill/hydration, auth-mode selection, file/canvas ingest, stalled runs.
- Use `slack-mirror-search` for keyword/semantic queries, relevance sanity checks, scoped retrieval.
- Use `slack-mirror-export` for channel/day exports, multi-day bundles, PDF formatting and attachments.

## Orchestration rules

1. Keep workspace explicit in every command (`--workspace ...`).
2. Preserve prior context (workspace/channel/day/terms) unless user changes it.
3. Prefer deterministic checks after actions (service status, queue counts, query validation).
4. When search quality is noisy, run lexical cross-checks and report both.
5. If a run stalls, stop and pivot to bounded/safer pass rather than waiting indefinitely.

## Minimal validation checklist

- Live ops change: verify webhooks + events + embeddings services are active.
- Ingest change: verify message/file/canvas counts moved as expected.
- Search change: verify keyword and semantic both return plausible hits.
- Export change: produce output artifact path(s) and message count.
