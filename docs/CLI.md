# `slack-mirror`
**Usage**

```
usage: slack-mirror [-h] [--config CONFIG]
                    {mirror,workspaces,channels,docs,completion} ...
```

**Options**

- `--config`
- `--help`
- `-h`

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

**Options**

- `--help`
- `-h`

**Subcommands**

- `sync-from-tool`

### `slack-mirror channels sync-from-tool`
**Usage**

```
usage: slack-mirror channels sync-from-tool [-h] [--json]
```

**Options**

- `--help`
- `--json`
- `-h`



## `slack-mirror completion`
**Usage**

```
usage: slack-mirror completion [-h] {print} ...
```

**Options**

- `--help`
- `-h`

**Subcommands**

- `print`

### `slack-mirror completion print`
**Usage**

```
usage: slack-mirror completion print [-h] {bash,zsh}
```

**Options**

- `--help`
- `-h`



## `slack-mirror docs`
**Usage**

```
usage: slack-mirror docs [-h] {generate} ...
```

**Options**

- `--help`
- `-h`

**Subcommands**

- `generate`

### `slack-mirror docs generate`
**Usage**

```
usage: slack-mirror docs generate [-h] [--format {markdown,man}]
                                  [--output OUTPUT]
```

**Options**

- `--format`
- `--help`
- `--output`
- `-h`



## `slack-mirror mirror`
**Usage**

```
usage: slack-mirror mirror [-h]
                           {init,backfill,serve-webhooks,process-events} ...
```

**Options**

- `--help`
- `-h`

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

- `--cache-root`
- `--channel-limit`
- `--download-content`
- `--file-types`
- `--help`
- `--include-files`
- `--include-messages`
- `--latest`
- `--oldest`
- `--workspace`
- `-h`


### `slack-mirror mirror init`
**Usage**

```
usage: slack-mirror mirror init [-h]
```

**Options**

- `--help`
- `-h`


### `slack-mirror mirror process-events`
**Usage**

```
usage: slack-mirror mirror process-events [-h] --workspace WORKSPACE
                                          [--limit LIMIT] [--loop]
                                          [--interval INTERVAL]
                                          [--max-cycles MAX_CYCLES]
```

**Options**

- `--help`
- `--interval`
- `--limit`
- `--loop`
- `--max-cycles`
- `--workspace`
- `-h`


### `slack-mirror mirror serve-webhooks`
**Usage**

```
usage: slack-mirror mirror serve-webhooks [-h] --workspace WORKSPACE
                                          [--bind BIND] [--port PORT]
```

**Options**

- `--bind`
- `--help`
- `--port`
- `--workspace`
- `-h`



## `slack-mirror workspaces`
**Usage**

```
usage: slack-mirror workspaces [-h] {list,sync-config,verify} ...
```

**Options**

- `--help`
- `-h`

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

- `--help`
- `--json`
- `-h`


### `slack-mirror workspaces sync-config`
**Usage**

```
usage: slack-mirror workspaces sync-config [-h]
```

**Options**

- `--help`
- `-h`


### `slack-mirror workspaces verify`
**Usage**

```
usage: slack-mirror workspaces verify [-h] [--workspace WORKSPACE]
```

**Options**

- `--help`
- `--workspace`
- `-h`
