# `slack-mirror`
Slack workspace mirror CLI for backfills, webhook ingest, and processing.

**Usage**

```
usage: slack-mirror [-h] [--config CONFIG]
                    {mirror,workspaces,channels,docs,completion} ...
```

**Options**

- `--config` — default: `config.yaml`

**Arguments**


**Subcommands**

- `channels`
- `completion`
- `docs`
- `mirror`
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
