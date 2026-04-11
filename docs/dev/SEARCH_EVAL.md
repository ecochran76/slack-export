# Search Evaluation + Rollout Gates

## Eval Harness

Script: `scripts/eval_search.py`

## Corpus modes

- `--corpus slack-db` (default): evaluate mirrored Slack DB
- `--corpus slack-corpus`: evaluate the broader message-plus-derived-text corpus
- `--corpus dir`: evaluate a directory/file corpus

### Slack DB run

```bash
PYTHONPATH=. python3 scripts/eval_search.py \
  --corpus slack-db \
  --db ./.local/state/slack_mirror_test.db \
  --workspace default \
  --dataset ./docs/dev/benchmarks/slack_smoke.jsonl \
  --mode hybrid \
  --limit 10
```

### Slack corpus run

```bash
PYTHONPATH=. python3 scripts/eval_search.py \
  --corpus slack-corpus \
  --db ./.local/state/slack_mirror_test.db \
  --workspace default \
  --dataset ./docs/dev/benchmarks/slack_corpus_smoke.jsonl \
  --mode hybrid \
  --limit 10
```

### Slack corpus depth run

```bash
PYTHONPATH=. python3 scripts/eval_search.py \
  --corpus slack-corpus \
  --db ./.local/state/slack_mirror_test.db \
  --workspace default \
  --dataset ./docs/dev/benchmarks/slack_corpus_depth.jsonl \
  --mode hybrid \
  --limit 10
```

### Directory run

```bash
PYTHONPATH=. python3 scripts/eval_search.py \
  --corpus dir \
  --path ./docs \
  --glob "**/*.md" \
  --dataset ./docs/dev/benchmarks/dir_docs_smoke.jsonl \
  --mode hybrid \
  --limit 10
```

Dataset format (`jsonl`):

```json
{"query":"deploy incident","relevant":{"C123:1740421200.123":2,"general:1740422200.555":1}}
{"query":"refund issue last sprint","relevant":{"dev/PHASE_E_SEMANTIC_SEARCH.md":2}}
```

ID conventions:
- Slack DB: `channel_id:ts` (or `channel_name:ts`)
- Slack corpus derived text: `source_kind:source_id:derivation_kind:extractor` (or `source_label`)
- Directory corpus: relative file path (e.g., `dev/SEARCH_EVAL.md`)

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

## Current P03 health contract

- `slack-mirror search health --workspace <name>`
- optional benchmark gate:
  - `slack-mirror search health --workspace <name> --dataset ./docs/dev/benchmarks/slack_corpus_smoke.jsonl`
  - `slack-mirror search health --workspace <name> --dataset ./docs/dev/benchmarks/slack_corpus_depth.jsonl`
- API:
  - `GET /v1/workspaces/{workspace}/search/health`
- MCP:
  - `search.health`

Current default benchmark thresholds:

- `hit_at_3 >= 0.5`
- `hit_at_10 >= 0.8`
- `ndcg_at_k >= 0.6`
- `latency_ms_p95 <= 800`

Current benchmark diagnostics:

- per-query `query_reports` are included in benchmark output
- search health also reports `degraded_queries` for misses or weak ranking

## Suggested cadence

- Run benchmark before changing fusion weights.
- Run benchmark after each search-ranking change.
- Use the smoke dataset for fast guardrails and the depth dataset for long-document/chunk regressions.
- Save output in PR notes so quality movement is explicit.
