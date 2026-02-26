---
name: slack-mirror-ingest
description: Hydrate/backfill Slack Mirror workspaces (messages, files, canvases), handle auth-mode/token mismatches, and recover from stalled ingest runs. Use for requests like "hydrate second DB", "backfill files/canvases", "why did backfill stall", or "re-run safely in bounded mode".
---

# Slack Mirror Ingest

## Backfill strategy

1. Initialize/sync workspace config.
2. Backfill messages first.
3. Reindex keyword + run embedding backfill/processing.
4. Backfill files/canvases metadata.
5. Optionally do content download in bounded passes.

## Key commands

- `slack-mirror --config <cfg> mirror backfill --workspace <ws> --include-messages`
- `slack-mirror --config <cfg> search reindex-keyword --workspace <ws>`
- `slack-mirror --config <cfg> mirror embeddings-backfill --workspace <ws> --model local-hash-128`
- `slack-mirror --config <cfg> mirror process-embedding-jobs --workspace <ws> --limit <n>`
- `slack-mirror --config <cfg> mirror backfill --workspace <ws> --include-files --file-types all`

## Guardrails

- Use `--auth-mode user` when user token scopes are required.
- If file downloads stall, stop and run metadata-only pass first.
- Report counts explicitly (messages/files/canvases, processed/skipped/errored).
- Validate with one keyword + one semantic query after ingest.

## Common failure patterns

- `missing_scope` on files/canvases: update Slack app scopes and retry.
- silent long run/no progress: kill stuck process, rerun bounded pass.
- semantic poor quality: verify embeddings exist and model matches query path.
