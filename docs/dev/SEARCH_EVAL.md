# Search Evaluation + Rollout Gates

## Eval Harness

Script: `scripts/eval_search.py`

Run:

```bash
PYTHONPATH=. python3 scripts/eval_search.py \
  --db ./data/slack_mirror.db \
  --workspace default \
  --dataset ./docs/dev/search_eval_dataset.jsonl \
  --mode hybrid \
  --limit 10
```

Dataset format (`jsonl`):

```json
{"query":"deploy incident","relevant":{"C123:1740421200.123":2,"C123:1740422200.555":1}}
{"query":"refund issue last sprint","relevant":{"C999:1740020000.000":2}}
```

Relevance labels:
- `0` = not relevant (omit from map)
- `1` = relevant
- `2+` = highly relevant

## Reported Metrics

- `ndcg_at_k`
- `mrr_at_k`
- `hit_at_3`
- `hit_at_10`
- `latency_ms_p50`
- `latency_ms_p95`

## Rollout Gates (Phase E)

1. **No lexical regression**
   - lexical mode metrics should stay within tolerance vs baseline.
2. **Hybrid quality lift**
   - hybrid should exceed lexical on semantic query subset.
3. **Latency SLO**
   - target: P50 < 250ms, P95 < 800ms.
4. **Operational confidence**
   - embedding job error rate low and stable.
   - queue drains under normal ingest load.

## Suggested cadence

- Run benchmark before changing fusion weights.
- Run benchmark after each search-ranking change.
- Save output in PR notes so quality movement is explicit.
