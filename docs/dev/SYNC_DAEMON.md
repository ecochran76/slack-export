# First-class Sync/Daemon/Status Commands

To avoid ad-hoc recovery scripts as the primary UX, Slack Mirror now exposes first-class mirror operations:

## Mirror Sync (reconcile)

```bash
slack-mirror --config config.local.yaml mirror sync --workspace default
```

Behavior:
- backfills messages (and optionally files)
- ingests thread replies for roots with `reply_count > 0`
- can reindex keyword + refresh embeddings in same operation

## Mirror Status (coverage + freshness)

```bash
slack-mirror --config config.local.yaml mirror status --json
```

Reports by workspace/channel class:
- channel count
- zero-message channels
- stale channels (default: older than 24h)
- latest timestamp

## Mirror Daemon (unified loop)

```bash
slack-mirror --config config.local.yaml mirror daemon --interval 2 --reconcile-minutes 30
```

Loop responsibilities:
- process pending events
- process embedding jobs
- run periodic message reconcile sweep

## Notes

- `scripts/audit_mirror_completeness.py` and `scripts/catchup_mirror.sh` remain useful for ops/debugging, but core behavior should be driven via first-class `mirror` commands above.
