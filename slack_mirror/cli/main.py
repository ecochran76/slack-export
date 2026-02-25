from __future__ import annotations

import argparse
import hashlib
import json
import time
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


def _detect_token_mode(token: str | None) -> str:
    t = (token or "").strip()
    if t.startswith("xoxb-"):
        return "bot"
    if t.startswith("xoxp-"):
        return "user"
    return "unknown"


def _enforce_auth_mode(token: str | None, auth_mode: str, *, command_name: str) -> None:
    detected = _detect_token_mode(token)
    mode = (auth_mode or "bot").lower()

    if mode not in {"bot", "user"}:
        raise ValueError(f"Unsupported auth mode: {auth_mode}")

    if mode == "bot" and detected == "user":
        raise ValueError(
            f"{command_name}: detected a user token, but auth mode defaults to 'bot'. "
            "Re-run with --auth-mode user to explicitly allow user-token operation."
        )

    if mode == "user" and detected == "bot":
        raise ValueError(
            f"{command_name}: detected a bot token, but --auth-mode user was requested. "
            "Use --auth-mode bot (or omit the flag)."
        )


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
    _enforce_auth_mode(token, args.auth_mode, command_name="mirror backfill")

    if args.messages_only and not args.include_messages:
        raise ValueError("mirror backfill: --messages-only requires --include-messages")

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

    channels_override = [c.strip() for c in (args.channels or "").split(",") if c.strip()]

    counts = {"users": 0, "channels": 0}
    if not args.messages_only:
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
            channel_ids_override=channels_override or None,
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

    cfg = load_config(args.config)
    db_path = cfg.get("storage", {}).get("db_path", "./data/slack_mirror.db")
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    ws_row = get_workspace_by_name(conn, args.workspace)
    if not ws_row:
        raise ValueError(f"Workspace '{args.workspace}' not found in DB. Run workspaces sync-config first.")

    search_cfg = cfg.get("search", {})
    semantic_cfg = search_cfg.get("semantic", {})
    keyword_cfg = search_cfg.get("keyword", {})
    profiles = search_cfg.get("query_profiles", {})
    profile_cfg = profiles.get(args.profile, {}) if args.profile else {}

    mode = args.mode or profile_cfg.get("mode") or semantic_cfg.get("mode_default", "lexical")
    model = args.model or profile_cfg.get("model") or semantic_cfg.get("model", "local-hash-128")
    profile_sem_w = profile_cfg.get("semantic_weights", {})
    profile_kw_w = profile_cfg.get("keyword_weights", {})

    lexical_weight = float(args.lexical_weight if args.lexical_weight is not None else profile_sem_w.get("lexical", semantic_cfg.get("weights", {}).get("lexical", 0.6)))
    semantic_weight = float(args.semantic_weight if args.semantic_weight is not None else profile_sem_w.get("semantic", semantic_cfg.get("weights", {}).get("semantic", 0.4)))
    semantic_scale = float(args.semantic_scale if args.semantic_scale is not None else profile_sem_w.get("semantic_scale", semantic_cfg.get("weights", {}).get("semantic_scale", 10.0)))
    rank_term_weight = float(args.rank_term_weight if args.rank_term_weight is not None else profile_kw_w.get("term", keyword_cfg.get("weights", {}).get("term", 5.0)))
    rank_link_weight = float(args.rank_link_weight if args.rank_link_weight is not None else profile_kw_w.get("link", keyword_cfg.get("weights", {}).get("link", 1.0)))
    rank_thread_weight = float(args.rank_thread_weight if args.rank_thread_weight is not None else profile_kw_w.get("thread", keyword_cfg.get("weights", {}).get("thread", 0.5)))
    rank_recency_weight = float(args.rank_recency_weight if args.rank_recency_weight is not None else profile_kw_w.get("recency", keyword_cfg.get("weights", {}).get("recency", 2.0)))

    base_query = args.query
    if profile_cfg.get("query_prefix"):
        base_query = f"{profile_cfg.get('query_prefix')} {base_query}".strip()

    t0 = time.perf_counter()
    rows = search_messages(
        conn,
        workspace_id=int(ws_row["id"]),
        query=base_query,
        limit=args.limit,
        use_fts=not args.no_fts,
        mode=mode,
        model_id=model,
        lexical_weight=lexical_weight,
        semantic_weight=semantic_weight,
        semantic_scale=semantic_scale,
        rank_term_weight=rank_term_weight,
        rank_link_weight=rank_link_weight,
        rank_thread_weight=rank_thread_weight,
        rank_recency_weight=rank_recency_weight,
        rerank=args.rerank,
        rerank_top_n=args.rerank_top_n,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # Optional result shaping (PR-F2)
    if args.group_by_thread:
        grouped: dict[tuple[str, str], dict] = {}
        for r in rows:
            thread_root = str(r.get("thread_ts") or r.get("ts") or "")
            key = (str(r.get("channel_id") or ""), thread_root)
            score = float(r.get("_hybrid_score") or r.get("_score") or r.get("_semantic_score") or 0.0)
            current = grouped.get(key)
            current_score = float(current.get("_hybrid_score") or current.get("_score") or current.get("_semantic_score") or 0.0) if current else -1e9
            if current is None or score > current_score:
                grouped[key] = r
        rows = list(grouped.values())

    if args.dedupe:
        seen: set[str] = set()
        deduped: list[dict] = []
        for r in rows:
            text = " ".join((r.get("text") or "").lower().split())
            sig = hashlib.sha1(f"{r.get('channel_id')}|{text}".encode("utf-8")).hexdigest()
            if sig in seen:
                continue
            seen.add(sig)
            deduped.append(r)
        rows = deduped

    rows = rows[: max(1, args.limit)]

    def _snippet(text: str, query: str, max_chars: int) -> str:
        t = (text or "").replace("\n", " ").strip()
        if len(t) <= max_chars:
            return t
        terms = [tok for tok in query.replace('"', " ").split() if ":" not in tok and not tok.startswith("-")]
        lower = t.lower()
        idx = -1
        for term in terms:
            i = lower.find(term.lower())
            if i >= 0:
                idx = i
                break
        if idx < 0:
            return t[: max_chars - 1] + "…"
        start = max(0, idx - max_chars // 3)
        end = min(len(t), start + max_chars)
        out = t[start:end]
        if start > 0:
            out = "…" + out
        if end < len(t):
            out = out + "…"
        return out

    if args.json:
        if args.snippet_chars and args.snippet_chars > 0:
            for r in rows:
                r["snippet"] = _snippet(str(r.get("text") or ""), args.query, args.snippet_chars)
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            channel = r.get("channel_name") or r.get("channel_id")
            base = r.get("text") or ""
            text_out = _snippet(str(base), args.query, args.snippet_chars) if args.snippet_chars else str(base)
            line = f"[{channel}] ts={r.get('ts')} user={r.get('user_id')} text={text_out}"
            if args.explain:
                line += (
                    f" | src={r.get('_source')}"
                    f" lex={r.get('_lexical_score', r.get('_score', 0))}"
                    f" sem={r.get('_semantic_score', 0)}"
                    f" hyb={r.get('_hybrid_score', 0)}"
                )
            print(line)

    source_counts: dict[str, int] = {}
    for r in rows:
        src = str(r.get("_source") or "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

    print(
        f"Keyword search workspace={args.workspace} mode={mode} profile={args.profile or 'none'} query={base_query!r} "
        f"results={len(rows)} latency_ms={elapsed_ms:.2f} sources={source_counts}"
    )
    return 0


def cmd_search_semantic(args: argparse.Namespace) -> int:
    args.mode = "semantic"
    # Ensure all attributes expected by cmd_search_keyword exist with defaults
    if not hasattr(args, "lexical_weight"):
        args.lexical_weight = None
    if not hasattr(args, "semantic_weight"):
        args.semantic_weight = None
    if not hasattr(args, "semantic_scale"):
        args.semantic_scale = None
    if not hasattr(args, "rank_term_weight"):
        args.rank_term_weight = None
    if not hasattr(args, "rank_link_weight"):
        args.rank_link_weight = None
    if not hasattr(args, "rank_thread_weight"):
        args.rank_thread_weight = None
    if not hasattr(args, "rank_recency_weight"):
        args.rank_recency_weight = None
    if not hasattr(args, "no_fts"):
        args.no_fts = False
    if not hasattr(args, "group_by_thread"):
        args.group_by_thread = False
    if not hasattr(args, "dedupe"):
        args.dedupe = False
    if not hasattr(args, "snippet_chars"):
        args.snippet_chars = 280
    if not hasattr(args, "explain"):
        args.explain = False
    if not hasattr(args, "rerank"):
        args.rerank = False
    if not hasattr(args, "rerank_top_n"):
        args.rerank_top_n = 50
    if not hasattr(args, "profile"):
        args.profile = None
    return cmd_search_keyword(args)


def cmd_search_query_dir(args: argparse.Namespace) -> int:
    from slack_mirror.search.dir_adapter import query_directory

    rows = query_directory(
        root=args.path,
        query=args.query,
        mode=args.mode,
        glob=args.glob,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(f"[{r.get('path')}] score={r.get('_score')} snippet={r.get('snippet')}")
    print(
        f"Directory search path={args.path} mode={args.mode} query={args.query!r} results={len(rows)} glob={args.glob}"
    )
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


def cmd_embeddings_backfill(args: argparse.Namespace) -> int:
    from slack_mirror.sync.embeddings import backfill_message_embeddings

    db_path = _db_path_from_config(args.config)
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    ws_row = get_workspace_by_name(conn, args.workspace)
    if not ws_row:
        raise ValueError(f"Workspace '{args.workspace}' not found in DB. Run workspaces sync-config first.")

    result = backfill_message_embeddings(
        conn,
        workspace_id=int(ws_row["id"]),
        model_id=args.model,
        limit=args.limit,
    )
    print(
        f"Embeddings backfill workspace={args.workspace} model={args.model} "
        f"scanned={result['scanned']} embedded={result['embedded']} skipped={result['skipped']}"
    )
    return 0


def cmd_embeddings_process(args: argparse.Namespace) -> int:
    from slack_mirror.sync.embeddings import process_embedding_jobs

    db_path = _db_path_from_config(args.config)
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    ws_row = get_workspace_by_name(conn, args.workspace)
    if not ws_row:
        raise ValueError(f"Workspace '{args.workspace}' not found in DB. Run workspaces sync-config first.")

    result = process_embedding_jobs(
        conn,
        workspace_id=int(ws_row["id"]),
        model_id=args.model,
        limit=args.limit,
    )
    print(
        f"Embedding jobs workspace={args.workspace} model={args.model} jobs={result['jobs']} "
        f"processed={result['processed']} skipped={result['skipped']} errored={result['errored']}"
    )
    return 0 if result["errored"] == 0 else 1


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
            "slack-mirror --config config.yaml search keyword --workspace default --query \"release incident\" --mode hybrid",
            "slack-mirror --config config.yaml search semantic --workspace default --query \"refund issue last sprint\"",
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
  local mirror_sub="init backfill embeddings-backfill process-embedding-jobs serve-webhooks process-events"
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
        --auth-mode)
          COMPREPLY=( $(compgen -W "bot user" -- "$cur") )
          return 0
          ;;
      esac
      COMPREPLY=( $(compgen -W "--workspace --auth-mode --include-messages --messages-only --channels --channel-limit --oldest --latest --include-files --file-types --download-content --cache-root --model --bind --port --limit --loop --interval --max-cycles" -- "$cur") )
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
        COMPREPLY=( $(compgen -W "keyword semantic query-dir reindex-keyword" -- "$cur") )
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
        case "$prev" in
          --mode)
            COMPREPLY=( $(compgen -W "lexical semantic hybrid" -- "$cur") )
            return 0
            ;;
        esac
        COMPREPLY=( $(compgen -W "--workspace --profile --path --glob --query --limit --mode --model --lexical-weight --semantic-weight --semantic-scale --rank-term-weight --rank-link-weight --rank-thread-weight --rank-recency-weight --group-by-thread --dedupe --snippet-chars --explain --rerank --rerank-top-n --no-fts --json" -- "$cur") )
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
  mirror_sub=(init backfill embeddings-backfill process-embedding-jobs serve-webhooks process-events)
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
        '--auth-mode[auth mode guardrail]:mode:(bot user)' \
        '--include-messages[include messages]' \
        '--messages-only[skip users/channels bootstrap and pull messages only]' \
        '--channels[channel id csv for message-only mode]:channels:' \
        '--channel-limit[channel limit]:number:' \
        '--oldest[oldest message ts]:timestamp:' \
        '--latest[latest message ts]:timestamp:' \
        '--include-files[include files/canvases]' \
        '--file-types[file types csv or all]:types:(all images snippets gdocs zips pdfs)' \
        '--download-content[download file/canvas content]' \
        '--cache-root[cache root path]:path:_files' \
        '--model[embedding model id]:model:' \
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
        _describe 'search command' '(keyword semantic query-dir reindex-keyword)'
        return
      fi
      _arguments \
        '--workspace[workspace name]:workspace:_slack_mirror_workspaces' \
        '--profile[named query profile]:profile:' \
        '--path[directory root]:path:_files -/' \
        '--glob[file glob]:glob:' \
        '--query[keyword query]:query:' \
        '--limit[maximum result rows]:number:' \
        '--mode[search mode]:mode:(lexical semantic hybrid)' \
        '--model[embedding model id]:model:' \
        '--lexical-weight[hybrid lexical weight]:number:' \
        '--semantic-weight[hybrid semantic weight]:number:' \
        '--semantic-scale[semantic score scaling factor]:number:' \
        '--rank-term-weight[keyword term-frequency weight]:number:' \
        '--rank-link-weight[keyword link boost weight]:number:' \
        '--rank-thread-weight[keyword thread boost weight]:number:' \
        '--rank-recency-weight[keyword recency weight]:number:' \
        '--group-by-thread[group results by thread root]' \
        '--dedupe[collapse near-duplicate text]' \
        '--snippet-chars[snippet length]:number:' \
        '--explain[show score/source details]' \
        '--rerank[apply optional heuristic reranking]' \
        '--rerank-top-n[top N rerank window]:number:' \
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
    p_backfill.add_argument(
        "--auth-mode",
        choices=["bot", "user"],
        default="bot",
        help="auth guardrail mode; defaults to bot and requires explicit user override",
    )
    p_backfill.add_argument("--include-messages", action="store_true", help="include message history")
    p_backfill.add_argument(
        "--messages-only",
        action="store_true",
        help="skip users/channels bootstrap and only backfill messages",
    )
    p_backfill.add_argument(
        "--channels",
        help="optional CSV of channel IDs for message-only pulls (avoids channels bootstrap dependency)",
    )
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

    p_emb_backfill = mirror_sub.add_parser("embeddings-backfill", help="backfill message embeddings")
    p_emb_backfill.add_argument("--workspace", required=True, help="workspace name")
    p_emb_backfill.add_argument("--model", default="local-hash-128", help="embedding model id")
    p_emb_backfill.add_argument("--limit", type=int, default=1000, help="maximum messages to scan")
    p_emb_backfill.set_defaults(func=cmd_embeddings_backfill)

    p_emb_process = mirror_sub.add_parser("process-embedding-jobs", help="process queued embedding jobs")
    p_emb_process.add_argument("--workspace", required=True, help="workspace name")
    p_emb_process.add_argument("--model", default="local-hash-128", help="embedding model id")
    p_emb_process.add_argument("--limit", type=int, default=200, help="maximum jobs to process")
    p_emb_process.set_defaults(func=cmd_embeddings_process)

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
    p_search_kw.add_argument("--profile", default=None, help="named query profile from config search.query_profiles")
    p_search_kw.add_argument(
        "--query",
        required=True,
        help="query text (supports from:, channel:/source:, in:, before:, after:, is:, has:link, quoted phrases, and -term)",
    )
    p_search_kw.add_argument("--limit", type=int, default=20, help="maximum result rows")
    p_search_kw.add_argument(
        "--mode",
        choices=["lexical", "semantic", "hybrid"],
        default=None,
        help="search retrieval mode (default from config: search.semantic.mode_default)",
    )
    p_search_kw.add_argument("--model", default=None, help="embedding model id (default from config: search.semantic.model)")
    p_search_kw.add_argument("--lexical-weight", type=float, default=None, help="hybrid lexical score weight")
    p_search_kw.add_argument("--semantic-weight", type=float, default=None, help="hybrid semantic score weight")
    p_search_kw.add_argument("--semantic-scale", type=float, default=None, help="semantic score scaling factor")
    p_search_kw.add_argument("--rank-term-weight", type=float, default=None, help="keyword ranking term-frequency weight")
    p_search_kw.add_argument("--rank-link-weight", type=float, default=None, help="keyword ranking link-presence weight")
    p_search_kw.add_argument("--rank-thread-weight", type=float, default=None, help="keyword ranking thread boost weight")
    p_search_kw.add_argument("--rank-recency-weight", type=float, default=None, help="keyword ranking recency weight")
    p_search_kw.add_argument("--group-by-thread", action="store_true", help="return best result per thread root")
    p_search_kw.add_argument("--dedupe", action="store_true", help="collapse near-duplicate text results")
    p_search_kw.add_argument("--snippet-chars", type=int, default=280, help="snippet length for text output")
    p_search_kw.add_argument("--explain", action="store_true", help="show score/source details per result")
    p_search_kw.add_argument("--rerank", action="store_true", help="apply optional heuristic reranking")
    p_search_kw.add_argument("--rerank-top-n", type=int, default=50, help="top N rows to rerank when --rerank is enabled")
    p_search_kw.add_argument("--no-fts", action="store_true", help="disable FTS prefilter and use SQL fallback only")
    p_search_kw.add_argument("--json", action="store_true", help="json output")
    p_search_kw.set_defaults(func=cmd_search_keyword)

    p_search_sem = search_sub.add_parser("semantic", help="semantic search over mirrored messages")
    p_search_sem.add_argument("--workspace", required=True, help="workspace name")
    p_search_sem.add_argument("--profile", default=None, help="named query profile from config search.query_profiles")
    p_search_sem.add_argument(
        "--query",
        required=True,
        help="semantic query text (supports from:, channel:/source:, in:, before:, after:, is:, has:link, quoted phrases, and -term)",
    )
    p_search_sem.add_argument("--limit", type=int, default=20, help="maximum result rows")
    p_search_sem.add_argument("--model", default=None, help="embedding model id (default from config: search.semantic.model)")
    p_search_sem.add_argument("--group-by-thread", action="store_true", help="return best result per thread root")
    p_search_sem.add_argument("--dedupe", action="store_true", help="collapse near-duplicate text results")
    p_search_sem.add_argument("--snippet-chars", type=int, default=280, help="snippet length for text output")
    p_search_sem.add_argument("--explain", action="store_true", help="show score/source details per result")
    p_search_sem.add_argument("--rerank", action="store_true", help="apply optional heuristic reranking")
    p_search_sem.add_argument("--rerank-top-n", type=int, default=50, help="top N rows to rerank when --rerank is enabled")
    p_search_sem.add_argument("--json", action="store_true", help="json output")
    p_search_sem.set_defaults(func=cmd_search_semantic)

    p_search_dir = search_sub.add_parser("query-dir", help="search a directory corpus")
    p_search_dir.add_argument("--path", required=True, help="root directory")
    p_search_dir.add_argument("--query", required=True, help="query text")
    p_search_dir.add_argument("--mode", choices=["lexical", "semantic", "hybrid"], default="hybrid")
    p_search_dir.add_argument("--glob", default="**/*.md", help="file glob relative to root")
    p_search_dir.add_argument("--limit", type=int, default=20, help="maximum result rows")
    p_search_dir.add_argument("--json", action="store_true", help="json output")
    p_search_dir.set_defaults(func=cmd_search_query_dir)

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
