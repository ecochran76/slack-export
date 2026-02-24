# `slack-mirror`
Slack workspace mirror CLI for backfills, webhook ingest, and processing.

**Usage**

```
usage: slack-mirror [-h] [--config CONFIG]
                    {mirror,workspaces,channels,search,docs,completion} ...
```

**Options**

- `--config` — default: `config.yaml`

**Arguments**


**Examples**

```
slack-mirror --config config.yaml mirror init
slack-mirror --config config.yaml workspaces list --json
```

**Subcommands**

- `channels`
- `completion`
- `docs`
- `mirror`
- `search`
- `workspaces`

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



## `slack-mirror mirror`
**Usage**

```
usage: slack-mirror mirror [-h]
                           {init,backfill,serve-webhooks,process-events} ...
```

**Arguments**


**Subcommands**

- `backfill`
- `init`
- `process-events`
- `serve-webhooks`

### `slack-mirror mirror backfill`
**Usage**

```
usage: slack-mirror mirror backfill [-h] --workspace WORKSPACE
                                    [--include-messages]
                                    [--channel-limit CHANNEL_LIMIT]
                                    [--oldest OLDEST] [--latest LATEST]
                                    [--include-files]
                                    [--file-types FILE_TYPES]
                                    [--download-content]
                                    [--cache-root CACHE_ROOT]
```

**Options**

- `--workspace` — workspace name from config
- `--include-messages` — include message history
- `--channel-limit` — limit channels processed in this run
- `--oldest` — oldest message ts boundary (inclusive)
- `--latest` — latest message ts boundary (inclusive)
- `--include-files` — include files and canvases metadata
- `--file-types` — files.list types filter; use 'all' to fetch all non-canvas file types; default: `images,snippets,gdocs,zips,pdfs`
- `--download-content`
- `--cache-root` — default: `./cache`

**Examples**

```
slack-mirror --config config.yaml mirror backfill --workspace default --include-messages --channel-limit 10
slack-mirror --config config.yaml mirror backfill --workspace default --include-files --file-types all --cache-root ./cache
```


### `slack-mirror mirror init`
**Usage**

```
usage: slack-mirror mirror init [-h]
```


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



## `slack-mirror search`
**Usage**

```
usage: slack-mirror search [-h] {reindex-keyword,keyword} ...
```

**Arguments**


**Subcommands**

- `keyword`
- `reindex-keyword`

### `slack-mirror search keyword`
**Usage**

```
usage: slack-mirror search keyword [-h] --workspace WORKSPACE --query QUERY
                                   [--limit LIMIT] [--no-fts] [--json]
```

**Options**

- `--workspace` — workspace name
- `--query` — query text (supports from:, channel:, before:, after:, is:, has:link, quoted phrases, and -term)
- `--limit` — maximum result rows; default: `20`
- `--no-fts` — disable FTS prefilter and use SQL fallback only
- `--json` — json output

**Examples**

```
slack-mirror --config config.yaml search reindex-keyword --workspace default
slack-mirror --config config.yaml search keyword --workspace default --query deploy --limit 20
```


### `slack-mirror search reindex-keyword`
**Usage**

```
usage: slack-mirror search reindex-keyword [-h] --workspace WORKSPACE
```

**Options**

- `--workspace` — workspace name



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
```

**Options**

- `--workspace`
