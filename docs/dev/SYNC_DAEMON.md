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

Health-gate examples:

```bash
# Print per-row status plus one HEALTHY/UNHEALTHY summary line
slack-mirror --config config.local.yaml mirror status --healthy

# Default health gate (recommended): fail on zero-message gaps only,
# while still reporting stale/mirrored-inactive counts for observability.
slack-mirror --config config.local.yaml mirror status \
  --healthy --fail-on-gap --max-zero-msg 0 --stale-hours 24

# Strict mode (optional): also fail on stale threshold
slack-mirror --config config.local.yaml mirror status \
  --healthy --fail-on-gap --max-zero-msg 0 --max-stale 0 --stale-hours 24 --enforce-stale
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
