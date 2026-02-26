---
name: slack-mirror-search
description: Run and interpret Slack Mirror keyword/semantic/hybrid search with workspace/channel/date scoping and relevance cross-checks. Use for requests like "find X in workspace Y", "semantic search for terms", "search seems noisy", and "confirm indexing freshness via query behavior".
---

# Slack Mirror Search

## Query modes

- Semantic: concept match; may be noisy on niche terms.
- Keyword: literal precision; best for rare names/tickers/brands.
- Hybrid: combine both; useful default for broad queries.

## Core commands

- Semantic:
  - `slack-mirror --config <cfg> search semantic --workspace <ws> --query "..." --mode semantic --model local-hash-128 --limit <n> --json`
- Keyword:
  - `slack-mirror --config <cfg> search keyword --workspace <ws> --query "..." --limit <n> --json`
- Hybrid semantic path:
  - `... search semantic --mode hybrid ...`

## Relevance workflow

1. Run requested semantic query.
2. If results are noisy, run lexical companion query.
3. Return strongest hits with channel + ts + short quote.
4. Flag confidence and caveats.

## Reporting format

- Separate by query term when user gives multiple terms.
- For each hit include: channel, timestamp, excerpt, why relevant.
- State when lexical was used to rescue noisy semantic output.
