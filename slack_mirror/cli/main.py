from __future__ import annotations

import argparse
import json
from pathlib import Path

from slack_mirror.core.config import load_config
from slack_mirror.core.db import (
    apply_migrations,
    connect,
    get_workspace_by_name,
    insert_event,
    list_workspaces,
    upsert_workspace,
)
from slack_mirror.integrations import SlackChannelsAdapter


def cmd_mirror_init(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    db_path = cfg.get("storage", {}).get("db_path", "./data/slack_mirror.db")
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))
    print(f"Initialized DB at {db_path}")
    return 0


def _db_path_from_config(config_path: str) -> str:
    cfg = load_config(config_path)
    return cfg.get("storage", {}).get("db_path", "./data/slack_mirror.db")


def _workspace_configs(config_path: str) -> list[dict]:
    cfg = load_config(config_path)
    return cfg.get("workspaces", [])


def _workspace_config_by_name(config_path: str, name: str) -> dict:
    for ws in _workspace_configs(config_path):
        if ws.get("name") == name:
            return ws
    raise ValueError(f"Workspace '{name}' not found in config")


def cmd_workspaces_sync(args: argparse.Namespace) -> int:
    db_path = _db_path_from_config(args.config)
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    imported = 0
    for ws in _workspace_configs(args.config):
        if not ws.get("name"):
            continue
        upsert_workspace(
            conn,
            name=ws.get("name"),
            team_id=ws.get("team_id"),
            domain=ws.get("domain"),
            config=ws,
        )
        imported += 1
    print(f"Synced {imported} workspaces into {db_path}")
    return 0


def cmd_workspaces_list(args: argparse.Namespace) -> int:
    db_path = _db_path_from_config(args.config)
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))
    rows = list_workspaces(conn)
    payload = [dict(r) for r in rows]
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for ws in payload:
            print(f"{ws.get('name')}\t{ws.get('team_id', '')}\t{ws.get('domain', '') or ''}")
    return 0


def cmd_workspaces_verify(args: argparse.Namespace) -> int:
    from slack_mirror.core.slack_api import safe_auth_test

    workspaces = _workspace_configs(args.config)
    if args.workspace:
        workspaces = [w for w in workspaces if w.get("name") == args.workspace]
    failures = 0
    for ws in workspaces:
        name = ws.get("name") or "<unnamed>"
        token = ws.get("token")
        if not token:
            failures += 1
            print(f"{name}\tmissing_token")
            continue
        ok, msg = safe_auth_test(token)
        status = "ok" if ok else "error"
        if not ok:
            failures += 1
        print(f"{name}\t{status}\t{msg}")
    return 1 if failures else 0


def cmd_mirror_backfill(args: argparse.Namespace) -> int:
    from slack_mirror.sync.backfill import (
        backfill_files_and_canvases,
        backfill_messages,
        backfill_users_and_channels,
    )

    db_path = _db_path_from_config(args.config)
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    ws_cfg = _workspace_config_by_name(args.config, args.workspace)
    token = ws_cfg.get("token")
    if not token:
        raise ValueError(f"Workspace '{args.workspace}' has no token configured")

    # Ensure workspace exists in DB
    workspace_id = upsert_workspace(
        conn,
        name=ws_cfg.get("name"),
        team_id=ws_cfg.get("team_id"),
        domain=ws_cfg.get("domain"),
        config=ws_cfg,
    )
    persisted = get_workspace_by_name(conn, ws_cfg.get("name"))
    if not persisted:
        raise RuntimeError("Failed to resolve workspace after upsert")

    counts = backfill_users_and_channels(token=token, workspace_id=workspace_id, conn=conn)
    message_counts = {"channels": 0, "messages": 0, "skipped": 0}
    if args.include_messages:
        message_counts = backfill_messages(
            token=token,
            workspace_id=workspace_id,
            conn=conn,
            channel_limit=args.channel_limit,
            oldest=args.oldest,
            latest=args.latest,
        )

    file_counts = {"files": 0, "canvases": 0, "files_downloaded": 0, "canvases_downloaded": 0}
    if args.include_files:
        file_counts = backfill_files_and_canvases(
            token=token,
            workspace_id=workspace_id,
            conn=conn,
            cache_root=args.cache_root,
            download_content=args.download_content,
            file_types=args.file_types,
        )

    print(
        "Backfill complete "
        f"workspace={ws_cfg.get('name')} users={counts['users']} channels={counts['channels']} "
        f"message_channels={message_counts['channels']} messages={message_counts['messages']} "
        f"skipped_channels={message_counts['skipped']} files={file_counts['files']} canvases={file_counts['canvases']} "
        f"files_downloaded={file_counts['files_downloaded']} canvases_downloaded={file_counts['canvases_downloaded']}"
    )
    return 0


def cmd_serve_webhooks(args: argparse.Namespace) -> int:
    from slack_mirror.service.server import run_webhook_server

    db_path = _db_path_from_config(args.config)
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    ws_cfg = _workspace_config_by_name(args.config, args.workspace)
    workspace_id = upsert_workspace(
        conn,
        name=ws_cfg.get("name"),
        team_id=ws_cfg.get("team_id"),
        domain=ws_cfg.get("domain"),
        config=ws_cfg,
    )

    signing_secret = ws_cfg.get("signing_secret")
    if not signing_secret:
        raise ValueError(f"Workspace '{args.workspace}' has no signing_secret configured")

    bind = args.bind or load_config(args.config).get("service", {}).get("bind", "127.0.0.1")
    port = args.port or int(load_config(args.config).get("service", {}).get("port", 8787))

    def on_event(payload: dict):
        event_id = payload.get("event_id") or f"evt_{payload.get('event_time','0')}"
        event_ts = str(payload.get("event_time") or "")
        event_type = (payload.get("event") or {}).get("type") or payload.get("type")
        insert_event(conn, workspace_id, event_id, event_ts, event_type, payload, status="pending")

    run_webhook_server(bind=bind, port=port, signing_secret=signing_secret, on_event=on_event)
    return 0


def cmd_process_events(args: argparse.Namespace) -> int:
    from slack_mirror.service.processor import process_pending_events, run_processor_loop

    db_path = _db_path_from_config(args.config)
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    ws_cfg = _workspace_config_by_name(args.config, args.workspace)
    ws_row = get_workspace_by_name(conn, ws_cfg.get("name"))
    if not ws_row:
        workspace_id = upsert_workspace(
            conn,
            name=ws_cfg.get("name"),
            team_id=ws_cfg.get("team_id"),
            domain=ws_cfg.get("domain"),
            config=ws_cfg,
        )
    else:
        workspace_id = int(ws_row["id"])

    if args.loop:
        result = run_processor_loop(
            conn,
            workspace_id,
            limit=args.limit,
            interval_seconds=args.interval,
            max_cycles=args.max_cycles,
        )
        print(
            f"Processor loop workspace={ws_cfg.get('name')} cycles={result['cycles']} "
            f"processed={result['processed']} errored={result['errored']}"
        )
        return 0 if result["errored"] == 0 else 1

    result = process_pending_events(conn, workspace_id, limit=args.limit)
    print(
        f"Processed events workspace={ws_cfg.get('name')} scanned={result['scanned']} "
        f"processed={result['processed']} errored={result['errored']}"
    )
    return 0 if result["errored"] == 0 else 1


def cmd_search_keyword(args: argparse.Namespace) -> int:
    from slack_mirror.search.keyword import search_messages

    db_path = _db_path_from_config(args.config)
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    ws_row = get_workspace_by_name(conn, args.workspace)
    if not ws_row:
        raise ValueError(f"Workspace '{args.workspace}' not found in DB. Run workspaces sync-config first.")

    rows = search_messages(
        conn,
        workspace_id=int(ws_row["id"]),
        query=args.query,
        limit=args.limit,
        use_fts=not args.no_fts,
    )

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            channel = r.get("channel_name") or r.get("channel_id")
            print(f"[{channel}] ts={r.get('ts')} user={r.get('user_id')} text={r.get('text') or ''}")

    print(f"Keyword search workspace={args.workspace} query={args.query!r} results={len(rows)}")
    return 0


def cmd_search_reindex(args: argparse.Namespace) -> int:
    from slack_mirror.search.keyword import reindex_messages_fts

    db_path = _db_path_from_config(args.config)
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    ws_row = get_workspace_by_name(conn, args.workspace)
    if not ws_row:
        raise ValueError(f"Workspace '{args.workspace}' not found in DB. Run workspaces sync-config first.")

    count = reindex_messages_fts(conn, workspace_id=int(ws_row["id"]))
    print(f"Reindexed messages_fts workspace={args.workspace} rows={count}")
    return 0


def cmd_channels_sync_from_tool(args: argparse.Namespace) -> int:
    adapter = SlackChannelsAdapter()
    mappings = adapter.list_mappings()
    if args.json:
        print(json.dumps(mappings, indent=2))
    else:
        for name, cid in mappings.items():
            print(f"{name}\t{cid}")
    return 0


def _find_subparser_action(parser: argparse.ArgumentParser):
    for action in parser._actions:  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            return action
    return None


def _example_commands_for(cmd: str) -> list[str]:
    examples = {
        "slack-mirror": [
            "slack-mirror --config config.yaml mirror init",
            "slack-mirror --config config.yaml workspaces list --json",
        ],
        "slack-mirror mirror backfill": [
            "slack-mirror --config config.yaml mirror backfill --workspace default --include-messages --channel-limit 10",
            "slack-mirror --config config.yaml mirror backfill --workspace default --include-files --file-types all --cache-root ./cache",
        ],
        "slack-mirror mirror serve-webhooks": [
            "slack-mirror --config config.yaml mirror serve-webhooks --workspace default --bind 127.0.0.1 --port 8787",
        ],
        "slack-mirror mirror process-events": [
            "slack-mirror --config config.yaml mirror process-events --workspace default --limit 200",
            "slack-mirror --config config.yaml mirror process-events --workspace default --loop --interval 2 --max-cycles 10",
        ],
        "slack-mirror search keyword": [
            "slack-mirror --config config.yaml search reindex-keyword --workspace default",
            "slack-mirror --config config.yaml search keyword --workspace default --query deploy --limit 20",
        ],
        "slack-mirror docs generate": [
            "slack-mirror --config config.yaml docs generate --format markdown --output docs/CLI.md",
            "slack-mirror --config config.yaml docs generate --format man --output docs/slack-mirror.1",
        ],
    }
    return examples.get(cmd, [])


def _emit_markdown_for_parser(parser: argparse.ArgumentParser, cmd: str = "slack-mirror", depth: int = 2) -> list[str]:
    lines: list[str] = []
    heading = "#" * depth
    lines.append(f"{heading} `{cmd}`")

    if parser.description:
        lines.append(parser.description)
        lines.append("")

    usage = parser.format_usage().strip()
    if usage:
        lines.append("**Usage**")
        lines.append("")
        lines.append("```")
        lines.append(usage)
        lines.append("```")
        lines.append("")

    option_actions = [
        a
        for a in parser._actions  # noqa: SLF001
        if a.option_strings and not isinstance(a, argparse._HelpAction)  # noqa: SLF001
    ]
    if option_actions:
        lines.append("**Options**")
        lines.append("")
        for action in option_actions:
            flags = ", ".join(f"`{f}`" for f in action.option_strings)
            details: list[str] = []
            if getattr(action, "help", None):
                details.append(str(action.help))
            default = getattr(action, "default", None)
            if default not in (None, argparse.SUPPRESS, False):
                details.append(f"default: `{default}`")
            line = f"- {flags}"
            if details:
                line += f" — {'; '.join(details)}"
            lines.append(line)
        lines.append("")

    positional_actions = [
        a
        for a in parser._actions  # noqa: SLF001
        if not a.option_strings and a.dest not in {"help"}
    ]
    if positional_actions:
        lines.append("**Arguments**")
        lines.append("")
        for action in positional_actions:
            if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
                continue
            name = getattr(action, "metavar", None) or action.dest
            detail = str(action.help) if getattr(action, "help", None) else ""
            if detail:
                lines.append(f"- `{name}` — {detail}")
            else:
                lines.append(f"- `{name}`")
        lines.append("")

    examples = _example_commands_for(cmd)
    if examples:
        lines.append("**Examples**")
        lines.append("")
        lines.append("```")
        lines.extend(examples)
        lines.append("```")
        lines.append("")

    sub = _find_subparser_action(parser)
    if sub:
        lines.append("**Subcommands**")
        lines.append("")
        for name in sorted(sub.choices.keys()):
            lines.append(f"- `{name}`")
        lines.append("")

        for name in sorted(sub.choices.keys()):
            child = sub.choices[name]
            lines.extend(_emit_markdown_for_parser(child, cmd=f"{cmd} {name}", depth=min(depth + 1, 6)))
            lines.append("")

    return lines


def _markdown_to_man(markdown_text: str, name: str = "slack-mirror") -> str:
    lines = [
        f".TH {name.upper()} 1",
        ".SH NAME",
        f"{name} - CLI documentation",
    ]
    for raw in markdown_text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("#"):
            title = line.lstrip("#").strip().strip("`")
            lines.append(f".SH {title.upper()}")
        elif line.startswith("- "):
            lines.append(f".IP \\[bu] 2\n{line[2:]}")
        else:
            cleaned = line.replace("`", "")
            lines.append(cleaned)
    lines.append("")
    return "\n".join(lines)


def cmd_docs_generate(args: argparse.Namespace) -> int:
    parser = build_parser()
    markdown = "\n".join(_emit_markdown_for_parser(parser, cmd="slack-mirror", depth=1)).strip() + "\n"

    output = args.output
    if args.format == "markdown":
        content = markdown
        output = output or "docs/CLI.md"
    else:
        content = _markdown_to_man(markdown, name="slack-mirror")
        output = output or "docs/slack-mirror.1"

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"Generated {args.format} docs at {out_path}")
    return 0


def _emit_bash_completion() -> str:
    return r'''# bash completion for slack-mirror
_slack_mirror_complete() {
  local cur prev words cword
  COMPREPLY=()
  _get_comp_words_by_ref -n : cur prev words cword 2>/dev/null || {
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
  }

  local top="mirror workspaces channels search docs completion"
  local mirror_sub="init backfill serve-webhooks process-events"
  local ws_sub="list sync-config verify"
  local channels_sub="sync-from-tool"
  local docs_sub="generate"
  local completion_sub="print"

  if [[ ${#COMP_WORDS[@]} -le 2 ]]; then
    COMPREPLY=( $(compgen -W "$top" -- "$cur") )
    return 0
  fi

  case "${COMP_WORDS[1]}" in
    mirror)
      if [[ ${#COMP_WORDS[@]} -le 3 ]]; then
        COMPREPLY=( $(compgen -W "$mirror_sub" -- "$cur") )
        return 0
      fi
      case "$prev" in
        --workspace)
          local w
          w=$(slack-mirror --config "${SLACK_MIRROR_CONFIG:-config.yaml}" workspaces list --json 2>/dev/null | python3 -c 'import json,sys
try:
 d=json.load(sys.stdin)
 print(" ".join([x.get("name","") for x in d if x.get("name")]))
except Exception:
 pass')
          COMPREPLY=( $(compgen -W "$w" -- "$cur") )
          return 0
          ;;
        --file-types)
          COMPREPLY=( $(compgen -W "all images snippets gdocs zips pdfs" -- "$cur") )
          return 0
          ;;
      esac
      COMPREPLY=( $(compgen -W "--workspace --include-messages --channel-limit --oldest --latest --include-files --file-types --download-content --cache-root --bind --port --limit --loop --interval --max-cycles" -- "$cur") )
      ;;
    workspaces)
      if [[ ${#COMP_WORDS[@]} -le 3 ]]; then
        COMPREPLY=( $(compgen -W "$ws_sub" -- "$cur") )
      else
        COMPREPLY=( $(compgen -W "--workspace --json" -- "$cur") )
      fi
      ;;
    channels)
      if [[ ${#COMP_WORDS[@]} -le 3 ]]; then
        COMPREPLY=( $(compgen -W "$channels_sub" -- "$cur") )
      else
        COMPREPLY=( $(compgen -W "--json" -- "$cur") )
      fi
      ;;
    search)
      if [[ ${#COMP_WORDS[@]} -le 3 ]]; then
        COMPREPLY=( $(compgen -W "keyword reindex-keyword" -- "$cur") )
      else
        case "$prev" in
          --workspace)
            local w
            w=$(slack-mirror --config "${SLACK_MIRROR_CONFIG:-config.yaml}" workspaces list --json 2>/dev/null | python3 -c 'import json,sys
try:
 d=json.load(sys.stdin)
 print(" ".join([x.get("name","") for x in d if x.get("name")]))
except Exception:
 pass')
            COMPREPLY=( $(compgen -W "$w" -- "$cur") )
            return 0
            ;;
        esac
        COMPREPLY=( $(compgen -W "--workspace --query --limit --no-fts --json" -- "$cur") )
      fi
      ;;
    docs)
      COMPREPLY=( $(compgen -W "$docs_sub" -- "$cur") )
      ;;
    completion)
      if [[ ${#COMP_WORDS[@]} -le 3 ]]; then
        COMPREPLY=( $(compgen -W "$completion_sub" -- "$cur") )
      else
        COMPREPLY=( $(compgen -W "bash zsh" -- "$cur") )
      fi
      ;;
  esac
  return 0
}
complete -F _slack_mirror_complete slack-mirror
'''


def _emit_zsh_completion() -> str:
    return r'''#compdef slack-mirror

_slack_mirror_workspaces() {
  local -a vals
  vals=(${(f)"$(slack-mirror --config ${SLACK_MIRROR_CONFIG:-config.yaml} workspaces list --json 2>/dev/null | python3 -c 'import json,sys
try:
 d=json.load(sys.stdin)
 print("\n".join([x.get("name","") for x in d if x.get("name")]))
except Exception:
 pass')"})
  _describe 'workspace' vals
}

_slack_mirror() {
  local -a top mirror_sub ws_sub
  top=(mirror workspaces channels search docs completion)
  mirror_sub=(init backfill serve-webhooks process-events)
  ws_sub=(list sync-config verify)

  if (( CURRENT == 2 )); then
    _describe 'command' top
    return
  fi

  case $words[2] in
    mirror)
      if (( CURRENT == 3 )); then
        _describe 'mirror command' mirror_sub
        return
      fi
      _arguments \
        '--workspace[workspace name]:workspace:_slack_mirror_workspaces' \
        '--include-messages[include messages]' \
        '--channel-limit[channel limit]:number:' \
        '--oldest[oldest message ts]:timestamp:' \
        '--latest[latest message ts]:timestamp:' \
        '--include-files[include files/canvases]' \
        '--file-types[file types csv or all]:types:(all images snippets gdocs zips pdfs)' \
        '--download-content[download file/canvas content]' \
        '--cache-root[cache root path]:path:_files' \
        '--bind[bind address]:address:' \
        '--port[port]:port:' \
        '--limit[event limit]:number:' \
        '--loop[loop mode]' \
        '--interval[loop interval seconds]:number:' \
        '--max-cycles[max loop cycles]:number:'
      ;;
    workspaces)
      if (( CURRENT == 3 )); then
        _describe 'workspaces command' ws_sub
        return
      fi
      _arguments '--workspace[workspace name]:workspace:_slack_mirror_workspaces' '--json[json output]'
      ;;
    channels)
      _arguments '--json[json output]'
      ;;
    search)
      if (( CURRENT == 3 )); then
        _describe 'search command' '(keyword reindex-keyword)'
        return
      fi
      _arguments \
        '--workspace[workspace name]:workspace:_slack_mirror_workspaces' \
        '--query[keyword query]:query:' \
        '--limit[maximum result rows]:number:' \
        '--no-fts[disable FTS prefilter]' \
        '--json[json output]'
      ;;
    completion)
      if (( CURRENT == 3 )); then
        _describe 'completion command' '(print)'
      elif (( CURRENT == 4 )); then
        _describe 'shell' '(bash zsh)'
      fi
      ;;
  esac
}

_slack_mirror "$@"
'''


def cmd_completion(args: argparse.Namespace) -> int:
    shell = args.shell
    if shell == "bash":
        print(_emit_bash_completion())
    elif shell == "zsh":
        print(_emit_zsh_completion())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slack-mirror",
        description="Slack workspace mirror CLI for backfills, webhook ingest, and processing.",
    )
    parser.add_argument("--config", default="config.yaml")

    sub = parser.add_subparsers(dest="command")

    mirror = sub.add_parser("mirror", help="mirror ingestion and processing commands")
    mirror_sub = mirror.add_subparsers(dest="mirror_cmd")
    p_init = mirror_sub.add_parser("init", help="initialize sqlite storage and apply migrations")
    p_init.set_defaults(func=cmd_mirror_init)
    p_backfill = mirror_sub.add_parser("backfill", help="run API backfill into local DB/cache")
    p_backfill.add_argument("--workspace", required=True, help="workspace name from config")
    p_backfill.add_argument("--include-messages", action="store_true", help="include message history")
    p_backfill.add_argument("--channel-limit", type=int, help="limit channels processed in this run")
    p_backfill.add_argument("--oldest", help="oldest message ts boundary (inclusive)")
    p_backfill.add_argument("--latest", help="latest message ts boundary (inclusive)")
    p_backfill.add_argument("--include-files", action="store_true", help="include files and canvases metadata")
    p_backfill.add_argument(
        "--file-types",
        default="images,snippets,gdocs,zips,pdfs",
        help="files.list types filter; use 'all' to fetch all non-canvas file types",
    )
    p_backfill.add_argument("--download-content", action="store_true")
    p_backfill.add_argument("--cache-root", default="./cache")
    p_backfill.set_defaults(func=cmd_mirror_backfill)

    p_serve = mirror_sub.add_parser("serve-webhooks", help="run Slack events webhook receiver")
    p_serve.add_argument("--workspace", required=True)
    p_serve.add_argument("--bind")
    p_serve.add_argument("--port", type=int)
    p_serve.set_defaults(func=cmd_serve_webhooks)

    p_process = mirror_sub.add_parser("process-events", help="process pending webhook events from DB")
    p_process.add_argument("--workspace", required=True)
    p_process.add_argument("--limit", type=int, default=100)
    p_process.add_argument("--loop", action="store_true")
    p_process.add_argument("--interval", type=float, default=2.0)
    p_process.add_argument("--max-cycles", type=int)
    p_process.set_defaults(func=cmd_process_events)

    workspaces = sub.add_parser("workspaces", help="workspace config/bootstrap/verification commands")
    ws_sub = workspaces.add_subparsers(dest="ws_cmd")
    p_ws_list = ws_sub.add_parser("list")
    p_ws_list.add_argument("--json", action="store_true")
    p_ws_list.set_defaults(func=cmd_workspaces_list)
    p_ws_sync = ws_sub.add_parser("sync-config")
    p_ws_sync.set_defaults(func=cmd_workspaces_sync)
    p_ws_verify = ws_sub.add_parser("verify")
    p_ws_verify.add_argument("--workspace")
    p_ws_verify.set_defaults(func=cmd_workspaces_verify)

    channels = sub.add_parser("channels", help="channel mapping integration helpers")
    channels_sub = channels.add_subparsers(dest="channels_cmd")
    p_sync = channels_sub.add_parser("sync-from-tool")
    p_sync.add_argument("--json", action="store_true")
    p_sync.set_defaults(func=cmd_channels_sync_from_tool)

    search = sub.add_parser("search", help="local keyword/semantic search commands")
    search_sub = search.add_subparsers(dest="search_cmd")
    p_search_reindex = search_sub.add_parser("reindex-keyword", help="rebuild messages_fts index for a workspace")
    p_search_reindex.add_argument("--workspace", required=True, help="workspace name")
    p_search_reindex.set_defaults(func=cmd_search_reindex)

    p_search_kw = search_sub.add_parser("keyword", help="keyword search over mirrored messages")
    p_search_kw.add_argument("--workspace", required=True, help="workspace name")
    p_search_kw.add_argument(
        "--query",
        required=True,
        help="query text (supports from:, channel:, before:, after:, is:, has:link, quoted phrases, and -term)",
    )
    p_search_kw.add_argument("--limit", type=int, default=20, help="maximum result rows")
    p_search_kw.add_argument("--no-fts", action="store_true", help="disable FTS prefilter and use SQL fallback only")
    p_search_kw.add_argument("--json", action="store_true", help="json output")
    p_search_kw.set_defaults(func=cmd_search_keyword)

    docs = sub.add_parser("docs", help="CLI docs generation commands")
    docs_sub = docs.add_subparsers(dest="docs_cmd")
    p_docs = docs_sub.add_parser("generate")
    p_docs.add_argument("--format", choices=["markdown", "man"], default="markdown")
    p_docs.add_argument("--output")
    p_docs.set_defaults(func=cmd_docs_generate)

    completion = sub.add_parser("completion", help="shell completion script emitters")
    p_completion = completion.add_subparsers(dest="completion_cmd")
    p_comp = p_completion.add_parser("print")
    p_comp.add_argument("shell", choices=["bash", "zsh"])
    p_comp.set_defaults(func=cmd_completion)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
