# Benchmark Fixtures

Benchmark datasets are JSONL files consumed by `search health` and `search profile-benchmark`.

## Row Shape

Each row must include:

- `query`: the search text to run
- `relevant`: a map of stable result labels to integer relevance weights

Rows may also include:

- `id`: a stable query id such as `live-q001`
- `intent`: a short non-content category such as `exact_keyword`, `paraphrase`, or `source_lookup`
- `notes`: authoring notes, if they do not expose private message text

## Label Rules

Use stable IDs only. Do not include Slack message bodies, snippets, user names, or private context in fixtures or committed benchmark reports.

Supported labels:

- message by channel id or channel name plus timestamp: `C123:1700000000.000100` or `general:1700000000.000100`
- derived text by stable source tuple: `file:F123:attachment_text:utf8_text`
- derived text by source label only for synthetic fixtures where the label is intentionally public and unambiguous

Before using a live fixture as evidence, validate it:

```bash
slack-mirror search benchmark-validate \
  --workspace default \
  --dataset docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl \
  --profiles baseline,local-bge-http,local-bge-http-rerank \
  --json
```

Then compare profiles:

```bash
slack-mirror search profile-benchmark \
  --workspace default \
  --dataset docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl \
  --profiles baseline,local-bge-http,local-bge-http-rerank \
  --json
```

If validation reports incomplete coverage for a profile model, treat relevance results as rollout-limited rather than model-quality evidence.
