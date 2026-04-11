# `slack-mirror`
Slack workspace mirror CLI for backfills, webhook ingest, and processing.

**Usage**

```
usage: slack-mirror [-h] [--version] [--config CONFIG]
                    {mirror,workspaces,channels,messages,search,docs,completion,api,mcp,user-env,version}
                    ...
```

**Options**

- `--version` — show program's version number and exit
- `--config` — config path; if omitted, search ./config.local.yaml, ./config.yaml, then ~/.config/slack-mirror/config.yaml

**Arguments**


**Examples**

```
slack-mirror --config config.yaml mirror init
slack-mirror --config config.yaml workspaces list --json
```

**Subcommands**

- `api`
- `channels`
- `completion`
- `docs`
- `mcp`
- `messages`
- `mirror`
- `search`
- `user-env`
- `version`
- `workspaces`

## `slack-mirror api`
**Usage**

```
usage: slack-mirror api [-h] {serve} ...
```

**Arguments**


**Subcommands**

- `serve`

### `slack-mirror api serve`
**Usage**

```
usage: slack-mirror api serve [-h] [--bind BIND] [--port PORT]
```

**Options**

- `--bind` — bind address; default: `127.0.0.1`
- `--port` — listen port; default: `8788`



## `slack-mirror channels`
**Usage**

```
usage: slack-mirror channels [-h] {sync-from-tool} ...
```

**Arguments**


**Subcommands**

- `sync-from-tool`

### `slack-mirror channels sync-from-tool`
**Usage**

```
usage: slack-mirror channels sync-from-tool [-h] [--json]
```

**Options**

- `--json`



## `slack-mirror completion`
**Usage**

```
usage: slack-mirror completion [-h] {print} ...
```

**Arguments**


**Subcommands**

- `print`

### `slack-mirror completion print`
**Usage**

```
usage: slack-mirror completion print [-h] {bash,zsh}
```

**Arguments**

- `shell`



## `slack-mirror docs`
**Usage**

```
usage: slack-mirror docs [-h] {generate} ...
```

**Arguments**


**Subcommands**

- `generate`

### `slack-mirror docs generate`
**Usage**

```
usage: slack-mirror docs generate [-h] [--format {markdown,man}]
                                  [--output OUTPUT]
```

**Options**

- `--format` — default: `markdown`
- `--output`

**Examples**

```
slack-mirror --config config.yaml docs generate --format markdown --output docs/CLI.md
slack-mirror --config config.yaml docs generate --format man --output docs/slack-mirror.1
```



## `slack-mirror mcp`
**Usage**

```
usage: slack-mirror mcp [-h] {serve} ...
```

**Arguments**


**Subcommands**

- `serve`

### `slack-mirror mcp serve`
**Usage**

```
usage: slack-mirror mcp serve [-h]
```



## `slack-mirror messages`
**Usage**

```
usage: slack-mirror messages [-h] {list} ...
```

**Arguments**


**Subcommands**

- `list`

### `slack-mirror messages list`
**Usage**

```
usage: slack-mirror messages list [-h] --workspace WORKSPACE [--after AFTER]
                                  [--before BEFORE] [--channels CHANNELS]
                                  [--limit LIMIT] [--json]
```

**Options**

- `--workspace` — workspace name
- `--after` — minimum timestamp (inclusive)
- `--before` — maximum timestamp (inclusive)
- `--channels` — comma-separated list of channel IDs or names
- `--limit` — maximum results; default: `1000`
- `--json`



## `slack-mirror mirror`
**Usage**

```
usage: slack-mirror mirror [-h]
                           {init,backfill,embeddings-backfill,process-embedding-jobs,oauth-callback,serve-webhooks,serve-socket-mode,process-events,sync,status,daemon}
                           ...
```

**Arguments**


**Subcommands**

- `backfill`
- `daemon`
- `embeddings-backfill`
- `init`
- `oauth-callback`
- `process-embedding-jobs`
- `process-events`
- `serve-socket-mode`
- `serve-webhooks`
- `status`
- `sync`

### `slack-mirror mirror backfill`
**Usage**

```
usage: slack-mirror mirror backfill [-h] --workspace WORKSPACE
                                    [--auth-mode {bot,user}]
                                    [--include-messages] [--messages-only]
                                    [--channels CHANNELS]
                                    [--channel-limit CHANNEL_LIMIT]
                                    [--oldest OLDEST] [--latest LATEST]
                                    [--include-files]
                                    [--file-types FILE_TYPES]
                                    [--download-content]
                                    [--cache-root CACHE_ROOT]
```

**Options**

- `--workspace` — workspace name from config
- `--auth-mode` — auth guardrail mode; defaults to bot and requires explicit user override; default: `bot`
- `--include-messages` — include message history
- `--messages-only` — skip users/channels bootstrap and only backfill messages
- `--channels` — optional CSV of channel IDs for message-only pulls (avoids channels bootstrap dependency)
- `--channel-limit` — limit channels processed in this run
- `--oldest` — oldest message ts boundary (inclusive)
- `--latest` — latest message ts boundary (inclusive)
- `--include-files` — include files and canvases metadata
- `--file-types` — files.list types filter; use 'all' to fetch all non-canvas file types; default: `images,snippets,gdocs,zips,pdfs`
- `--download-content`
- `--cache-root` — override cache root (defaults to storage.cache_root from config)

**Examples**

```
slack-mirror --config config.yaml mirror backfill --workspace default --include-messages --channel-limit 10
slack-mirror --config config.yaml mirror backfill --workspace default --include-files --file-types all --cache-root ./cache
```


### `slack-mirror mirror daemon`
**Usage**

```
usage: slack-mirror mirror daemon [-h] [--workspace WORKSPACE]
                                  [--interval INTERVAL]
                                  [--event-limit EVENT_LIMIT]
                                  [--embedding-limit EMBEDDING_LIMIT]
                                  [--model MODEL]
                                  [--reconcile-minutes RECONCILE_MINUTES]
                                  [--reconcile-channel-limit RECONCILE_CHANNEL_LIMIT]
                                  [--auth-mode {bot,user}]
                                  [--cache-root CACHE_ROOT]
                                  [--max-cycles MAX_CYCLES]
```

**Options**

- `--workspace` — optional workspace name (default: all workspaces)
- `--interval` — loop interval in seconds; default: `2.0`
- `--event-limit` — default: `1000`
- `--embedding-limit` — default: `1000`
- `--model` — embedding model id; default: `local-hash-128`
- `--reconcile-minutes` — periodic reconcile cadence (0 disables); default: `30.0`
- `--reconcile-channel-limit` — default: `300`
- `--auth-mode` — auth mode for reconcile backfill; default: `user`
- `--cache-root` — reserved for future file-cache reconcile support; defaults to storage.cache_root from config
- `--max-cycles`


### `slack-mirror mirror embeddings-backfill`
**Usage**

```
usage: slack-mirror mirror embeddings-backfill [-h] --workspace WORKSPACE
                                               [--model MODEL] [--limit LIMIT]
```

**Options**

- `--workspace` — workspace name
- `--model` — embedding model id; default: `local-hash-128`
- `--limit` — maximum messages to scan; default: `1000`


### `slack-mirror mirror init`
**Usage**

```
usage: slack-mirror mirror init [-h]
```


### `slack-mirror mirror oauth-callback`
**Usage**

```
usage: slack-mirror mirror oauth-callback [-h] --workspace WORKSPACE
                                          [--client-id CLIENT_ID]
                                          [--client-secret CLIENT_SECRET]
                                          [--bind BIND] [--port PORT]
                                          [--callback-path CALLBACK_PATH]
                                          [--redirect-uri REDIRECT_URI]
                                          --cert-file CERT_FILE --key-file
                                          KEY_FILE [--scopes SCOPES]
                                          [--user-scopes USER_SCOPES]
                                          [--state STATE] [--timeout TIMEOUT]
                                          [--open-browser]
```

**Options**

- `--workspace` — workspace name from config
- `--client-id` — Slack app client ID (defaults to workspace config client_id)
- `--client-secret` — Slack app client secret (defaults to workspace config client_secret)
- `--bind` — HTTPS callback bind host; default: `localhost`
- `--port` — HTTPS callback port; default: `3000`
- `--callback-path` — OAuth callback path; default: `/slack/oauth/callback`
- `--redirect-uri` — explicit redirect URI (must match Slack app config)
- `--cert-file` — TLS cert PEM file (mkcert localhost cert)
- `--key-file` — TLS key PEM file (mkcert localhost key)
- `--scopes` — comma-separated bot scopes; default: ``
- `--user-scopes` — comma-separated user scopes; default: ``
- `--state` — optional OAuth state override
- `--timeout` — callback wait timeout in seconds; default: `180`
- `--open-browser` — open install URL automatically

**Examples**

```
slack-mirror --config config.yaml mirror oauth-callback --workspace default --cert-file ./localhost+2.pem --key-file ./localhost+2-key.pem --scopes chat:write,channels:history --open-browser
```


### `slack-mirror mirror process-embedding-jobs`
**Usage**

```
usage: slack-mirror mirror process-embedding-jobs [-h] --workspace WORKSPACE
                                                  [--model MODEL]
                                                  [--limit LIMIT]
```

**Options**

- `--workspace` — workspace name
- `--model` — embedding model id; default: `local-hash-128`
- `--limit` — maximum jobs to process; default: `200`


### `slack-mirror mirror process-events`
**Usage**

```
usage: slack-mirror mirror process-events [-h] --workspace WORKSPACE
                                          [--limit LIMIT] [--loop]
                                          [--interval INTERVAL]
                                          [--max-cycles MAX_CYCLES]
```

**Options**

- `--workspace`
- `--limit` — default: `100`
- `--loop`
- `--interval` — default: `2.0`
- `--max-cycles`

**Examples**

```
slack-mirror --config config.yaml mirror process-events --workspace default --limit 200
slack-mirror --config config.yaml mirror process-events --workspace default --loop --interval 2 --max-cycles 10
```


### `slack-mirror mirror serve-socket-mode`
**Usage**

```
usage: slack-mirror mirror serve-socket-mode [-h] --workspace WORKSPACE
```

**Options**

- `--workspace`

**Examples**

```
slack-mirror --config config.yaml mirror serve-socket-mode --workspace default
```


### `slack-mirror mirror serve-webhooks`
**Usage**

```
usage: slack-mirror mirror serve-webhooks [-h] --workspace WORKSPACE
                                          [--bind BIND] [--port PORT]
```

**Options**

- `--workspace`
- `--bind`
- `--port`

**Examples**

```
slack-mirror --config config.yaml mirror serve-webhooks --workspace default --bind 127.0.0.1 --port 8787
```


### `slack-mirror mirror status`
**Usage**

```
usage: slack-mirror mirror status [-h] [--workspace WORKSPACE]
                                  [--stale-hours STALE_HOURS] [--healthy]
                                  [--fail-on-gap]
                                  [--max-zero-msg MAX_ZERO_MSG]
                                  [--max-stale MAX_STALE] [--enforce-stale]
                                  [--classify-access]
                                  [--classify-limit CLASSIFY_LIMIT] [--json]
```

**Options**

- `--workspace` — optional workspace name
- `--stale-hours` — stale threshold in hours; default: `24.0`
- `--healthy` — emit HEALTHY/UNHEALTHY summary
- `--fail-on-gap` — exit code 2 when unhealthy
- `--max-zero-msg` — max zero-message channels allowed per row
- `--max-stale` — max stale channels allowed per row
- `--enforce-stale` — include stale threshold in health gate (default: observe stale but do not fail)
- `--classify-access` — include A/B/C access classification and C-bucket channel ids
- `--classify-limit` — max zero-message channel ids to print per workspace for classification; default: `200`
- `--json`


### `slack-mirror mirror sync`
**Usage**

```
usage: slack-mirror mirror sync [-h] [--workspace WORKSPACE]
                                [--auth-mode {bot,user}] [--include-files]
                                [--file-types FILE_TYPES] [--download-content]
                                [--cache-root CACHE_ROOT] [--messages-only]
                                [--channels CHANNELS]
                                [--channel-limit CHANNEL_LIMIT]
                                [--oldest OLDEST] [--latest LATEST]
                                [--refresh-embeddings] [--model MODEL]
                                [--embedding-scan-limit EMBEDDING_SCAN_LIMIT]
                                [--embedding-job-limit EMBEDDING_JOB_LIMIT]
                                [--reindex-keyword]
```

**Options**

- `--workspace` — optional workspace name (default: all workspaces)
- `--auth-mode` — auth mode for backfill; default: `user`
- `--include-files` — include files/canvases metadata
- `--file-types` — files.list types filter; default: `all`
- `--download-content` — download file/canvas content
- `--cache-root` — override cache root (defaults to storage.cache_root from config)
- `--messages-only` — skip users/channels bootstrap and pull messages only
- `--channels` — csv list of channel ids (messages-only mode)
- `--channel-limit` — cap channels processed
- `--oldest` — oldest message ts boundary (inclusive)
- `--latest` — latest message ts boundary (inclusive)
- `--refresh-embeddings` — enqueue and process embedding catch-up
- `--model` — embedding model id; default: `local-hash-128`
- `--embedding-scan-limit` — default: `50000`
- `--embedding-job-limit` — default: `5000`
- `--reindex-keyword` — rebuild FTS index after sync



## `slack-mirror search`
**Usage**

```
usage: slack-mirror search [-h]
                           {reindex-keyword,keyword,semantic,query-dir} ...
```

**Arguments**


**Subcommands**

- `keyword`
- `query-dir`
- `reindex-keyword`
- `semantic`

### `slack-mirror search keyword`
**Usage**

```
usage: slack-mirror search keyword [-h] --workspace WORKSPACE
                                   [--profile PROFILE] --query QUERY
                                   [--limit LIMIT]
                                   [--mode {lexical,semantic,hybrid}]
                                   [--model MODEL]
                                   [--lexical-weight LEXICAL_WEIGHT]
                                   [--semantic-weight SEMANTIC_WEIGHT]
                                   [--semantic-scale SEMANTIC_SCALE]
                                   [--rank-term-weight RANK_TERM_WEIGHT]
                                   [--rank-link-weight RANK_LINK_WEIGHT]
                                   [--rank-thread-weight RANK_THREAD_WEIGHT]
                                   [--rank-recency-weight RANK_RECENCY_WEIGHT]
                                   [--group-by-thread] [--dedupe]
                                   [--snippet-chars SNIPPET_CHARS] [--explain]
                                   [--rerank] [--rerank-top-n RERANK_TOP_N]
                                   [--no-fts] [--json]
```

**Options**

- `--workspace` — workspace name
- `--profile` — named query profile from config search.query_profiles
- `--query` — query text (supports from:, channel:/source:, in:, before:, after:, is:, has:link, quoted phrases, and -term)
- `--limit` — maximum result rows; default: `20`
- `--mode` — search retrieval mode (default from config: search.semantic.mode_default)
- `--model` — embedding model id (default from config: search.semantic.model)
- `--lexical-weight` — hybrid lexical score weight
- `--semantic-weight` — hybrid semantic score weight
- `--semantic-scale` — semantic score scaling factor
- `--rank-term-weight` — keyword ranking term-frequency weight
- `--rank-link-weight` — keyword ranking link-presence weight
- `--rank-thread-weight` — keyword ranking thread boost weight
- `--rank-recency-weight` — keyword ranking recency weight
- `--group-by-thread` — return best result per thread root
- `--dedupe` — collapse near-duplicate text results
- `--snippet-chars` — snippet length for text output; default: `280`
- `--explain` — show score/source details per result
- `--rerank` — apply optional heuristic reranking
- `--rerank-top-n` — top N rows to rerank when --rerank is enabled; default: `50`
- `--no-fts` — disable FTS prefilter and use SQL fallback only
- `--json` — json output

**Examples**

```
slack-mirror --config config.yaml search reindex-keyword --workspace default
slack-mirror --config config.yaml search keyword --workspace default --query deploy --limit 20
slack-mirror --config config.yaml search keyword --workspace default --query "release incident" --mode hybrid
slack-mirror --config config.yaml search semantic --workspace default --query "refund issue last sprint"
```


### `slack-mirror search query-dir`
**Usage**

```
usage: slack-mirror search query-dir [-h] --path PATH --query QUERY
                                     [--mode {lexical,semantic,hybrid}]
                                     [--glob GLOB] [--limit LIMIT] [--json]
```

**Options**

- `--path` — root directory
- `--query` — query text
- `--mode` — default: `hybrid`
- `--glob` — file glob relative to root; default: `**/*.md`
- `--limit` — maximum result rows; default: `20`
- `--json` — json output


### `slack-mirror search reindex-keyword`
**Usage**

```
usage: slack-mirror search reindex-keyword [-h] --workspace WORKSPACE
```

**Options**

- `--workspace` — workspace name


### `slack-mirror search semantic`
**Usage**

```
usage: slack-mirror search semantic [-h] --workspace WORKSPACE
                                    [--profile PROFILE] --query QUERY
                                    [--limit LIMIT] [--model MODEL]
                                    [--group-by-thread] [--dedupe]
                                    [--snippet-chars SNIPPET_CHARS]
                                    [--explain] [--rerank]
                                    [--rerank-top-n RERANK_TOP_N] [--json]
```

**Options**

- `--workspace` — workspace name
- `--profile` — named query profile from config search.query_profiles
- `--query` — semantic query text (supports from:, channel:/source:, in:, before:, after:, is:, has:link, quoted phrases, and -term)
- `--limit` — maximum result rows; default: `20`
- `--model` — embedding model id (default from config: search.semantic.model)
- `--group-by-thread` — return best result per thread root
- `--dedupe` — collapse near-duplicate text results
- `--snippet-chars` — snippet length for text output; default: `280`
- `--explain` — show score/source details per result
- `--rerank` — apply optional heuristic reranking
- `--rerank-top-n` — top N rows to rerank when --rerank is enabled; default: `50`
- `--json` — json output



## `slack-mirror user-env`
**Usage**

```
usage: slack-mirror user-env [-h]
                             {install,update,rollback,uninstall,status,validate-live,check-live,recover-live}
                             ...
```

**Arguments**


**Subcommands**

- `check-live`
- `install`
- `recover-live`
- `rollback`
- `status`
- `uninstall`
- `update`
- `validate-live`

### `slack-mirror user-env check-live`
**Usage**

```
usage: slack-mirror user-env check-live [-h] [--json]
```

**Options**

- `--json` — json output


### `slack-mirror user-env install`
**Usage**

```
usage: slack-mirror user-env install [-h]
```


### `slack-mirror user-env recover-live`
**Usage**

```
usage: slack-mirror user-env recover-live [-h] [--apply] [--json]
```

**Options**

- `--apply` — execute the safe remediations
- `--json` — json output


### `slack-mirror user-env rollback`
**Usage**

```
usage: slack-mirror user-env rollback [-h]
```


### `slack-mirror user-env status`
**Usage**

```
usage: slack-mirror user-env status [-h] [--json]
```

**Options**

- `--json` — json output


### `slack-mirror user-env uninstall`
**Usage**

```
usage: slack-mirror user-env uninstall [-h] [--purge-data]
```

**Options**

- `--purge-data` — also remove config, DB, and cache


### `slack-mirror user-env update`
**Usage**

```
usage: slack-mirror user-env update [-h]
```


### `slack-mirror user-env validate-live`
**Usage**

```
usage: slack-mirror user-env validate-live [-h] [--json]
```

**Options**

- `--json` — json output



## `slack-mirror version`
**Usage**

```
usage: slack-mirror version [-h]
```


## `slack-mirror workspaces`
**Usage**

```
usage: slack-mirror workspaces [-h] {list,sync-config,verify} ...
```

**Arguments**


**Subcommands**

- `list`
- `sync-config`
- `verify`

### `slack-mirror workspaces list`
**Usage**

```
usage: slack-mirror workspaces list [-h] [--json]
```

**Options**

- `--json`


### `slack-mirror workspaces sync-config`
**Usage**

```
usage: slack-mirror workspaces sync-config [-h]
```


### `slack-mirror workspaces verify`
**Usage**

```
usage: slack-mirror workspaces verify [-h] [--workspace WORKSPACE]
                                      [--require-explicit-outbound]
```

**Options**

- `--workspace`
- `--require-explicit-outbound` — fail when outbound_token/outbound_user_token are not explicitly configured
