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

# Access classification: A (mirrored+inactive), B (active recent), C (zero-message)
slack-mirror --config config.local.yaml mirror status \
  --json --classify-access --classify-limit 200
```

The classification payload is intended to explain stale warnings, not just count them. It now includes:

- total channels
- A/B/C percentages
- an interpretation label:
  - `active_recent_activity_present`
  - `mirrored_but_quiet`
  - `not_yet_mirrored`
- sample A-bucket and C-bucket channels
- channel class on sample entries
- last-message age for A-bucket samples
- split C-bucket counts for:
  - `shell_like` IM/MPIM channels
  - `unexpected_empty` public/private channels
- explicit status on C-bucket samples:
  - `shell_channel_no_messages`
  - `unexpected_empty_channel`

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
