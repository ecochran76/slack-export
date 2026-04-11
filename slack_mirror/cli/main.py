from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
import sqlite3
from urllib.parse import urlparse

from slack_mirror import __version__
from slack_mirror.core.config import load_config, resolve_config_path
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
    print(f"Initialized DB at {db_path} (config={_resolved_config_path(args.config)})")
    return 0


def _resolved_config_path(config_path: str | None) -> str:
    return str(resolve_config_path(config_path))


def _db_path_from_config(config_path: str | None) -> str:
    cfg = load_config(config_path)
    return cfg.get("storage", {}).get("db_path", "./data/slack_mirror.db")


def _cache_root_from_config(config_path: str | None) -> str:
    cfg = load_config(config_path)
    return cfg.get("storage", {}).get("cache_root", "./cache")


def _workspace_configs(config_path: str | None) -> list[dict]:
    cfg = load_config(config_path)
    return cfg.get("workspaces", [])


def _workspace_config_by_name(config_path: str | None, name: str) -> dict:
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
        if not workspaces:
            raise ValueError(f"Workspace '{args.workspace}' not found in config")
    failures = 0
    for ws in workspaces:
        name = ws.get("name") or "<unnamed>"
        if bool(getattr(args, "require_explicit_outbound", False)):
            outbound_token = ws.get("outbound_token") or ws.get("write_token")
            outbound_user_token = ws.get("outbound_user_token") or ws.get("write_user_token")
            if not outbound_token:
                failures += 1
                print(f"{name}\tmissing_outbound_token")
            if ws.get("user_token") and not outbound_user_token:
                failures += 1
                print(f"{name}\tmissing_outbound_user_token")
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
    auth_mode = (args.auth_mode or "bot").lower()
    token_key = "user_token" if auth_mode == "user" else "token"
    token = ws_cfg.get(token_key)
    if not token:
        raise ValueError(f"Workspace '{args.workspace}' has no {token_key} configured")
    _enforce_auth_mode(token, auth_mode, command_name="mirror backfill")

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
        cache_root = args.cache_root or _cache_root_from_config(args.config)
        file_counts = backfill_files_and_canvases(
            token=token,
            workspace_id=workspace_id,
            conn=conn,
            cache_root=cache_root,
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


def cmd_mirror_oauth_callback(args: argparse.Namespace) -> int:
    from slack_mirror.service.oauth import (
        build_install_url,
        exchange_oauth_code,
        format_tokens_summary,
        generate_state,
        maybe_open_browser,
        run_local_oauth_callback,
    )

    ws_cfg = _workspace_config_by_name(args.config, args.workspace)

    client_id = args.client_id or ws_cfg.get("client_id")
    client_secret = args.client_secret or ws_cfg.get("client_secret")
    if not client_id:
        raise ValueError("Missing client_id. Provide --client-id or set workspaces[].client_id in config")
    if not client_secret:
        raise ValueError("Missing client_secret. Provide --client-secret or set workspaces[].client_secret in config")

    bind = args.bind
    port = args.port
    callback_path = args.callback_path
    redirect_uri = args.redirect_uri or f"https://{bind}:{port}{callback_path}"

    parsed = urlparse(redirect_uri)
    if parsed.scheme != "https":
        raise ValueError("redirect_uri must be https://")

    state = args.state or generate_state()

    scopes = [s.strip() for s in (args.scopes or "").split(",") if s.strip()]
    user_scopes = [s.strip() for s in (args.user_scopes or "").split(",") if s.strip()]
    if not scopes and not user_scopes:
        raise ValueError("Provide --scopes and/or --user-scopes")

    install_url = build_install_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scopes=scopes,
        user_scopes=user_scopes or None,
        state=state,
    )

    print("Install URL:")
    print(install_url)

    if args.open_browser:
        maybe_open_browser(install_url)

    print(
        f"Listening for OAuth callback on https://{bind}:{port}{callback_path} "
        f"(timeout={args.timeout}s)"
    )
    cb = run_local_oauth_callback(
        bind=bind,
        port=port,
        callback_path=callback_path,
        cert_file=args.cert_file,
        key_file=args.key_file,
        timeout_seconds=args.timeout,
        expected_state=state,
    )
    if cb.error:
        raise RuntimeError(f"OAuth callback returned error: {cb.error}")

    token_payload = exchange_oauth_code(
        client_id=client_id,
        client_secret=client_secret,
        code=cb.code,
        redirect_uri=redirect_uri,
    )

    print("\nOAuth token exchange complete:")
    print(format_tokens_summary(token_payload))
    print("\nSuggested config snippet:")
    print(
        f"workspaces:\n"
        f"  - name: {args.workspace}\n"
        f"    token: {token_payload.get('access_token', '')}\n"
        f"    user_token: {token_payload.get('authed_user', {}).get('access_token', '')}\n"
        f"    team_id: {token_payload.get('team', {}).get('id', ws_cfg.get('team_id', ''))}\n"
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


def cmd_serve_socket_mode(args: argparse.Namespace) -> int:
    from slack_mirror.service.server import run_socket_mode

    db_path = _db_path_from_config(args.config)
    conn = connect(db_path, check_same_thread=False)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    ws_cfg = _workspace_config_by_name(args.config, args.workspace)
    workspace_id = upsert_workspace(
        conn,
        name=ws_cfg.get("name"),
        team_id=ws_cfg.get("team_id"),
        domain=ws_cfg.get("domain"),
        config=ws_cfg,
    )

    app_token = ws_cfg.get("app_token")
    if not app_token:
        raise ValueError(f"Workspace '{args.workspace}' has no app_token configured (required for Socket Mode)")
    
    bot_token = ws_cfg.get("token")
    if not bot_token:
        raise ValueError(f"Workspace '{args.workspace}' has no bot token configured")

    def on_event(payload: dict):
        event_id = payload.get("event_id") or f"evt_{payload.get('event_time','0')}"
        event_ts = str(payload.get("event_time") or "")
        event_type = (payload.get("event") or {}).get("type") or payload.get("type")
        insert_event(conn, workspace_id, event_id, event_ts, event_type, payload, status="pending")

    run_socket_mode(app_token=app_token, bot_token=bot_token, on_event=on_event)
    return 0


def cmd_process_events(args: argparse.Namespace) -> int:
    from slack_mirror.service.app import get_app_service
    from slack_mirror.service.processor import run_processor_loop

    service = get_app_service(args.config)
    conn = service.connect()
    workspace_id = service.workspace_id(conn, args.workspace)

    if args.loop:
        result = run_processor_loop(
            conn,
            workspace_id,
            limit=args.limit,
            interval_seconds=args.interval,
            max_cycles=args.max_cycles,
        )
        print(
            f"Processor loop workspace={args.workspace} cycles={result['cycles']} "
            f"processed={result['processed']} errored={result['errored']}"
        )
        return 0 if result["errored"] == 0 else 1

    result = service.process_pending_events(conn, workspace=args.workspace, limit=args.limit)
    print(
        f"Processed events workspace={args.workspace} scanned={result['scanned']} "
        f"processed={result['processed']} errored={result['errored']}"
    )
    return 0 if result["errored"] == 0 else 1


def _workspace_names(config_path: str | None, workspace: str | None = None) -> list[str]:
    cfg = load_config(config_path)
    names = [ws.get("name") for ws in cfg.get("workspaces", []) if ws.get("name")]
    if workspace:
        if workspace not in names:
            raise ValueError(f"Workspace '{workspace}' not found in config")
        return [workspace]
    return names


def cmd_mirror_sync(args: argparse.Namespace) -> int:
    from slack_mirror.search.keyword import reindex_messages_fts
    from slack_mirror.sync.backfill import (
        backfill_files_and_canvases,
        backfill_messages,
        backfill_users_and_channels,
    )
    from slack_mirror.sync.embeddings import backfill_message_embeddings, process_embedding_jobs

    db_path = _db_path_from_config(args.config)
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    names = _workspace_names(args.config, args.workspace)
    auth_mode = (args.auth_mode or "user").lower()

    for ws_name in names:
        ws_cfg = _workspace_config_by_name(args.config, ws_name)
        token_key = "user_token" if auth_mode == "user" else "token"
        token = ws_cfg.get(token_key)
        if not token:
            raise ValueError(f"Workspace '{ws_name}' has no {token_key} configured")
        _enforce_auth_mode(token, auth_mode, command_name="mirror sync")

        ws_row = get_workspace_by_name(conn, ws_name)
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

        if not args.messages_only:
            backfill_users_and_channels(token=token, workspace_id=workspace_id, conn=conn)

        channels_override = [c.strip() for c in (args.channels or "").split(",") if c.strip()]
        msg_stats = backfill_messages(
            token=token,
            workspace_id=workspace_id,
            conn=conn,
            channel_limit=args.channel_limit,
            oldest=args.oldest,
            latest=args.latest,
            channel_ids_override=channels_override or None,
        )

        if args.include_files:
            cache_root = args.cache_root or _cache_root_from_config(args.config)
            backfill_files_and_canvases(
                token=token,
                workspace_id=workspace_id,
                conn=conn,
                cache_root=cache_root,
                download_content=bool(args.download_content),
                file_types=args.file_types,
            )

        if args.refresh_embeddings:
            backfill_message_embeddings(
                conn,
                workspace_id=workspace_id,
                model_id=args.model,
                limit=args.embedding_scan_limit,
            )
            process_embedding_jobs(
                conn,
                workspace_id=workspace_id,
                model_id=args.model,
                limit=args.embedding_job_limit,
            )

        if args.reindex_keyword:
            rows = reindex_messages_fts(conn, workspace_id=workspace_id)
            print(f"[sync] reindex-keyword workspace={ws_name} rows={rows}")

        print(
            f"[sync] workspace={ws_name} message_channels={msg_stats.get('channels', 0)} messages={msg_stats.get('messages', 0)} skipped={msg_stats.get('skipped', 0)}"
        )
    return 0


def cmd_mirror_status(args: argparse.Namespace) -> int:
    from slack_mirror.service.app import get_app_service

    service = get_app_service(args.config)
    conn = service.connect()
    if args.workspace:
        ws_row = get_workspace_by_name(conn, args.workspace)
        if not ws_row:
            raise ValueError(f"Workspace '{args.workspace}' not found in DB. Run workspaces sync-config first.")
    summary, out = service.get_workspace_status(
        conn,
        workspace=args.workspace,
        stale_hours=float(args.stale_hours),
        max_zero_msg=int(args.max_zero_msg),
        max_stale=int(args.max_stale),
        enforce_stale=bool(args.enforce_stale),
    )

    unhealthy_rows = [r for r in out if r.health_reasons]

    access_classification = None
    if args.classify_access:
        stale_cutoff_ts = time.time() - (float(args.stale_hours) * 3600.0)
        where_ws = ""
        if args.workspace:
            where_ws = " and w.name=?"
        q_cls = f"""
        with last_msg as (
          select workspace_id, channel_id, max(cast(ts as real)) as max_ts, count(*) as msg_count
          from messages
          group by workspace_id, channel_id
        )
        select w.name as workspace,
               sum(case when coalesce(lm.msg_count,0)=0 then 1 else 0 end) as zero_message_channels,
               sum(case when coalesce(lm.msg_count,0)>0 and lm.max_ts < ? then 1 else 0 end) as mirrored_inactive_channels,
               sum(case when coalesce(lm.msg_count,0)>0 and lm.max_ts >= ? then 1 else 0 end) as active_recent_channels
        from channels c
        join workspaces w on w.id=c.workspace_id
        left join last_msg lm on lm.workspace_id=c.workspace_id and lm.channel_id=c.channel_id
        {where_ws}
        group by w.name
        order by w.name
        """
        cls_params: list[object] = [stale_cutoff_ts, stale_cutoff_ts]
        if args.workspace:
            cls_params.append(args.workspace)
        cls_rows = conn.execute(q_cls, tuple(cls_params)).fetchall()
        details = []
        for ws, zero_cnt, inactive_cnt, active_cnt in cls_rows:
            q_ids = f"""
            with msg_ch as (
              select workspace_id, channel_id, count(*) as msg_count
              from messages
              group by workspace_id, channel_id
            )
            select c.channel_id
            from channels c
            join workspaces w on w.id=c.workspace_id
            left join msg_ch m on m.workspace_id=c.workspace_id and m.channel_id=c.channel_id
            where w.name=? and coalesce(m.msg_count,0)=0
            order by c.channel_id
            limit ?
            """
            ids = [r[0] for r in conn.execute(q_ids, (ws, int(args.classify_limit))).fetchall()]
            details.append(
                {
                    "workspace": ws,
                    "A_mirrored_inactive": int(inactive_cnt or 0),
                    "B_active_recent": int(active_cnt or 0),
                    "C_zero_message": int(zero_cnt or 0),
                    "C_zero_message_channel_ids": ids,
                    "C_zero_message_ids_truncated": bool(int(zero_cnt or 0) > len(ids)),
                }
            )
        access_classification = details

    if args.json:
        payload: object
        if args.healthy:
            payload = {
                "summary": summary.__dict__,
                "rows": [r.__dict__ for r in out],
            }
        else:
            payload = [r.__dict__ for r in out]
        if access_classification is not None:
            if isinstance(payload, dict):
                payload = {**payload, "access_classification": access_classification}
            else:
                payload = {"rows": payload, "access_classification": access_classification}
        print(json.dumps(payload, indent=2))
        if args.fail_on_gap and not summary.healthy:
            return 2
        return 0

    if args.healthy:
        print("workspace\tclass\tchannels\tzero_msg\tstale\tmirrored_inactive\tlatest_ts\treasons")
    else:
        print("workspace\tclass\tchannels\tzero_msg\tstale\tmirrored_inactive\tlatest_ts")
    for r in out:
        row = (
            f"{r.workspace}\t{r.channel_class}\t{r.channels}\t{r.zero_msg_channels}\t{r.stale_channels}\t{r.mirrored_inactive_channels}\t{r.latest_ts or '-'}"
        )
        if args.healthy:
            row += f"\t{', '.join(r.health_reasons) if r.health_reasons else '-'}"
        print(row)

    if args.healthy:
        if not args.enforce_stale:
            print("NOTE stale counts shown for observability; health gate currently enforces zero_msg only")
        if summary.healthy:
            print("HEALTHY")
        else:
            top = unhealthy_rows[0]
            why = ", ".join(top.health_reasons)
            print(f"UNHEALTHY {top.workspace}/{top.channel_class}: {why}")

    if access_classification is not None:
        print("\nAccess classification (A mirrored+inactive, B active_recent, C zero_message):")
        for r in access_classification:
            print(
                f"- {r['workspace']}: A={r['A_mirrored_inactive']} B={r['B_active_recent']} C={r['C_zero_message']}"
            )
            if r["C_zero_message_channel_ids"]:
                ids = ",".join(r["C_zero_message_channel_ids"])
                suffix = " ..." if r["C_zero_message_ids_truncated"] else ""
                print(f"  C_ids: {ids}{suffix}")

    if args.fail_on_gap and not summary.healthy:
        return 2
    return 0 if summary.healthy else 1


def cmd_mirror_daemon(args: argparse.Namespace) -> int:
    from slack_mirror.service.processor import process_pending_events
    from slack_mirror.sync.backfill import backfill_messages
    from slack_mirror.sync.embeddings import process_embedding_jobs

    db_path = _db_path_from_config(args.config)
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    names = _workspace_names(args.config, args.workspace)
    ws_state: dict[str, dict[str, object]] = {}
    for ws_name in names:
        ws_cfg = _workspace_config_by_name(args.config, ws_name)
        ws_row = get_workspace_by_name(conn, ws_name)
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
        token_key = "user_token" if (args.auth_mode or "user") == "user" else "token"
        token = ws_cfg.get(token_key)
        if not token:
            raise ValueError(f"Workspace '{ws_name}' has no {token_key} configured")
        ws_state[ws_name] = {"id": workspace_id, "token": token}

    print(f"Starting mirror daemon for workspaces: {', '.join(names)}")
    last_reconcile = 0.0
    cycle = 0
    while True:
        cycle += 1
        for ws_name in names:
            state = ws_state[ws_name]
            process_pending_events(conn, int(state["id"]), limit=args.event_limit)
            process_embedding_jobs(
                conn,
                workspace_id=int(state["id"]),
                model_id=args.model,
                limit=args.embedding_limit,
            )

        if args.reconcile_minutes > 0 and (time.time() - last_reconcile) >= args.reconcile_minutes * 60:
            for ws_name in names:
                state = ws_state[ws_name]
                backfill_messages(
                    token=str(state["token"]),
                    workspace_id=int(state["id"]),
                    conn=conn,
                    channel_limit=args.reconcile_channel_limit,
                )
            last_reconcile = time.time()
            print(f"[daemon] reconcile complete cycle={cycle}")

        if args.max_cycles and cycle >= args.max_cycles:
            print(f"[daemon] reached max cycles ({args.max_cycles}), exiting")
            return 0
        time.sleep(args.interval)


def cmd_messages_list(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    db_path = cfg.get("storage", {}).get("db_path", "./data/slack_mirror.db")
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    ws_row = get_workspace_by_name(conn, args.workspace)
    if not ws_row:
        raise ValueError(f"Workspace '{args.workspace}' not found in DB")
    workspace_id = int(ws_row["id"])

    clauses = ["m.workspace_id = ?", "m.deleted = 0"]
    params = [workspace_id]

    if args.after:
        clauses.append("CAST(m.ts AS REAL) >= CAST(? AS REAL)")
        params.append(args.after)
    if args.before:
        clauses.append("CAST(m.ts AS REAL) <= CAST(? AS REAL)")
        params.append(args.before)

    if args.channels:
        channel_names = [c.strip() for c in args.channels.split(",") if c.strip()]
        if channel_names:
            ch_clauses = []
            for ch in channel_names:
                ch_clauses.append("""
                    (m.channel_id = ? OR m.channel_id IN (
                        SELECT channel_id FROM channels WHERE workspace_id = m.workspace_id AND lower(name) = lower(?)
                    ))
                """)
                params.extend([ch, ch])
            clauses.append("(" + " OR ".join(ch_clauses) + ")")

    where_sql = " AND ".join(clauses)
    query = f"""
        SELECT
            m.channel_id,
            COALESCE(ch.name, m.channel_id) AS channel_name,
            m.ts,
            m.user_id,
            COALESCE(u.display_name, u.real_name, u.username, m.user_id) AS user_label,
            m.text,
            m.subtype,
            m.thread_ts,
            m.edited_ts,
            m.deleted
        FROM messages m
        LEFT JOIN channels ch ON ch.workspace_id = m.workspace_id AND ch.channel_id = m.channel_id
        LEFT JOIN users u ON u.workspace_id = m.workspace_id AND u.user_id = m.user_id
        WHERE {where_sql}
        ORDER BY CAST(m.ts AS REAL) DESC
        LIMIT ?
    """
    params.append(args.limit)

    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(f"[{r['channel_name']}] {r['user_label']} @ {r['ts']}: {r['text'][:80]}")
    return 0

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
    # Respect an explicit --mode if provided; default to semantic for the alias.
    if not getattr(args, "mode", None):
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


def cmd_search_derived_text(args: argparse.Namespace) -> int:
    from slack_mirror.search.derived_text import search_derived_text

    db_path = _db_path_from_config(args.config)
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    ws_row = get_workspace_by_name(conn, args.workspace)
    if not ws_row:
        raise ValueError(f"Workspace '{args.workspace}' not found in DB. Run workspaces sync-config first.")

    rows = search_derived_text(
        conn,
        workspace_id=int(ws_row["id"]),
        query=args.query,
        limit=args.limit,
        derivation_kind=args.kind,
        source_kind=args.source_kind,
    )
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            snippet = str(row.get("matched_text") or row.get("text") or "").replace("\n", " ").strip()
            if len(snippet) > 140:
                snippet = snippet[:139] + "…"
            print(
                f"[{row.get('source_kind')}:{row.get('source_label')}] "
                f"kind={row.get('derivation_kind')} extractor={row.get('extractor')} "
                f"snippet={snippet}"
            )
    print(
        f"Derived-text search workspace={args.workspace} query={args.query!r} results={len(rows)} "
        f"kind={args.kind or 'any'} source_kind={args.source_kind or 'any'}"
    )
    return 0


def cmd_search_corpus(args: argparse.Namespace) -> int:
    from slack_mirror.service.app import get_app_service

    service = get_app_service(args.config)
    conn = service.connect()

    search_cfg = service.config.get("search", {})
    semantic_cfg = search_cfg.get("semantic", {})
    mode = args.mode or semantic_cfg.get("mode_default", "hybrid")
    model = args.model or semantic_cfg.get("model", "local-hash-128")
    lexical_weight = float(args.lexical_weight if args.lexical_weight is not None else semantic_cfg.get("weights", {}).get("lexical", 0.6))
    semantic_weight = float(args.semantic_weight if args.semantic_weight is not None else semantic_cfg.get("weights", {}).get("semantic", 0.4))
    semantic_scale = float(args.semantic_scale if args.semantic_scale is not None else semantic_cfg.get("weights", {}).get("semantic_scale", 10.0))

    rows = service.corpus_search(
        conn,
        workspace=args.workspace,
        all_workspaces=bool(args.all_workspaces),
        query=args.query,
        limit=args.limit,
        mode=mode,
        model_id=model,
        lexical_weight=lexical_weight,
        semantic_weight=semantic_weight,
        semantic_scale=semantic_scale,
        use_fts=not args.no_fts,
        derived_kind=args.kind,
        derived_source_kind=args.source_kind,
    )
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            workspace_label = str(row.get("workspace") or "").strip()
            label = row.get("source_label") or row.get("channel_name") or row.get("channel_id") or row.get("source_id")
            snippet = str(row.get("snippet_text") or row.get("matched_text") or row.get("text") or "").replace("\n", " ").strip()
            if len(snippet) > 160:
                snippet = snippet[:159] + "…"
            prefix = f"{workspace_label}/" if workspace_label else ""
            line = f"[{prefix}{row.get('result_kind')}:{label}] {snippet}"
            if args.explain:
                line += (
                    f" | src={row.get('_source')}"
                    f" lex={row.get('_lexical_score', row.get('_score', 0))}"
                    f" sem={row.get('_semantic_score', 0)}"
                    f" hyb={row.get('_hybrid_score', 0)}"
                )
            print(line)
    scope = "all" if args.all_workspaces else str(args.workspace)
    print(
        f"Corpus search workspace={scope} mode={mode} query={args.query!r} results={len(rows)} "
        f"kind={args.kind or 'any'} source_kind={args.source_kind or 'any'}"
    )
    return 0


def cmd_search_health(args: argparse.Namespace) -> int:
    from slack_mirror.service.app import get_app_service

    service = get_app_service(args.config)
    conn = service.connect()
    payload = service.search_health(
        conn,
        workspace=args.workspace,
        dataset_path=args.dataset,
        mode=args.mode,
        limit=args.limit,
        model_id=args.model,
        min_hit_at_3=args.min_hit_at_3,
        min_hit_at_10=args.min_hit_at_10,
        min_ndcg_at_k=args.min_ndcg_at_k,
        max_latency_p95_ms=args.max_latency_p95_ms,
    )
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        readiness = payload["readiness"]
        print(f"Search health workspace={payload['workspace']} status={payload['status']} readiness={readiness['status']}")
        attachment = readiness['derived_text']['attachment_text']
        ocr = readiness['derived_text']['ocr_text']
        print(
            "Readiness:"
            f" messages={readiness['messages']['count']}"
            f" embeddings.count={readiness['messages']['embeddings']['count']}"
            f" embeddings.pending={readiness['messages']['embeddings']['pending']}"
            f" embeddings.errors={readiness['messages']['embeddings']['errors']}"
            f" attachment.count={attachment['count']}"
            f" attachment.pending={attachment['pending']}"
            f" attachment.errors={attachment['errors']}"
            f" ocr.count={ocr['count']}"
            f" ocr.pending={ocr['pending']}"
            f" ocr.errors={ocr['errors']}"
        )
        if attachment.get('providers'):
            print("Attachment providers: " + ", ".join(f"{name}={count}" for name, count in sorted(attachment['providers'].items())))
        if attachment.get('issue_reasons'):
            print("Attachment issues: " + ", ".join(f"{name}={count}" for name, count in sorted(attachment['issue_reasons'].items())))
        if ocr.get('providers'):
            print("OCR providers: " + ", ".join(f"{name}={count}" for name, count in sorted(ocr['providers'].items())))
        if ocr.get('issue_reasons'):
            print("OCR issues: " + ", ".join(f"{name}={count}" for name, count in sorted(ocr['issue_reasons'].items())))
        if payload.get("benchmark"):
            bench = payload["benchmark"]
            print(
                "Benchmark:"
                f" mode={bench['mode']}"
                f" queries={bench['queries']}"
                f" hit@3={bench['hit_at_3']}"
                f" hit@10={bench['hit_at_10']}"
                f" ndcg@k={bench['ndcg_at_k']}"
                f" mrr@k={bench['mrr_at_k']}"
                f" p95_ms={bench['latency_ms_p95']}"
            )
        if payload["failure_codes"]:
            print("Failures: " + ", ".join(payload["failure_codes"]))
        if payload["warning_codes"]:
            print("Warnings: " + ", ".join(payload["warning_codes"]))
    return 0 if payload["status"] != "fail" else 1


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


def cmd_process_derived_text_jobs(args: argparse.Namespace) -> int:
    from slack_mirror.sync.derived_text import process_derived_text_jobs

    db_path = _db_path_from_config(args.config)
    conn = connect(db_path)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "core" / "migrations"))

    ws_row = get_workspace_by_name(conn, args.workspace)
    if not ws_row:
        raise ValueError(f"Workspace '{args.workspace}' not found in DB. Run workspaces sync-config first.")

    result = process_derived_text_jobs(
        conn,
        workspace_id=int(ws_row["id"]),
        derivation_kind=args.kind,
        limit=args.limit,
    )
    print(
        f"Derived-text jobs workspace={args.workspace} kind={args.kind} jobs={result['jobs']} "
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
        "slack-mirror mirror oauth-callback": [
            "slack-mirror --config config.yaml mirror oauth-callback --workspace default --cert-file ./localhost+2.pem --key-file ./localhost+2-key.pem --scopes chat:write,channels:history --open-browser",
        ],
        "slack-mirror mirror serve-webhooks": [
            "slack-mirror --config config.yaml mirror serve-webhooks --workspace default --bind 127.0.0.1 --port 8787",
        ],
        "slack-mirror mirror serve-socket-mode": [
            "slack-mirror --config config.yaml mirror serve-socket-mode --workspace default",
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

  local top="mirror workspaces channels search docs completion api mcp release user-env version"
  local api_sub="serve"
  local mcp_sub="serve"
  local release_sub="check"
  local user_env_sub="install update rollback uninstall status validate-live check-live recover-live"
  local mirror_sub="init backfill embeddings-backfill process-embedding-jobs process-derived-text-jobs oauth-callback serve-webhooks serve-socket-mode process-events sync status daemon"
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
      COMPREPLY=( $(compgen -W "--workspace --auth-mode --include-messages --messages-only --channels --channel-limit --oldest --latest --include-files --file-types --download-content --cache-root --model --bind --port --limit --loop --interval --max-cycles --client-id --client-secret --callback-path --redirect-uri --cert-file --key-file --scopes --user-scopes --state --timeout --open-browser --refresh-embeddings --embedding-scan-limit --embedding-job-limit --reindex-keyword --stale-hours --healthy --fail-on-gap --max-zero-msg --max-stale --enforce-stale --classify-access --classify-limit --json --event-limit --embedding-limit --reconcile-minutes --reconcile-channel-limit" -- "$cur") )
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
        COMPREPLY=( $(compgen -W "keyword semantic derived-text corpus health query-dir reindex-keyword" -- "$cur") )
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
        COMPREPLY=( $(compgen -W "--workspace --profile --path --glob --query --limit --mode --model --lexical-weight --semantic-weight --semantic-scale --rank-term-weight --rank-link-weight --rank-thread-weight --rank-recency-weight --group-by-thread --dedupe --snippet-chars --explain --rerank --rerank-top-n --no-fts --kind --source-kind --json" -- "$cur") )
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
    api)
      if [[ ${#COMP_WORDS[@]} -le 3 ]]; then
        COMPREPLY=( $(compgen -W "$api_sub" -- "$cur") )
        return 0
      fi
      COMPREPLY=( $(compgen -W "--bind --port" -- "$cur") )
      ;;
    mcp)
      if [[ ${#COMP_WORDS[@]} -le 3 ]]; then
        COMPREPLY=( $(compgen -W "$mcp_sub" -- "$cur") )
        return 0
      fi
      COMPREPLY=()
      ;;
    release)
      if [[ ${#COMP_WORDS[@]} -le 3 ]]; then
        COMPREPLY=( $(compgen -W "$release_sub" -- "$cur") )
        return 0
      fi
      COMPREPLY=( $(compgen -W "--json --require-clean --require-release-version" -- "$cur") )
      ;;
    user-env)
      if [[ ${#COMP_WORDS[@]} -le 3 ]]; then
        COMPREPLY=( $(compgen -W "$user_env_sub" -- "$cur") )
        return 0
      fi
      if [[ "${COMP_WORDS[2]}" == "uninstall" ]]; then
        COMPREPLY=( $(compgen -W "--purge-data" -- "$cur") )
      elif [[ "${COMP_WORDS[2]}" == "status" || "${COMP_WORDS[2]}" == "validate-live" || "${COMP_WORDS[2]}" == "check-live" ]]; then
        COMPREPLY=( $(compgen -W "--json" -- "$cur") )
      elif [[ "${COMP_WORDS[2]}" == "recover-live" ]]; then
        COMPREPLY=( $(compgen -W "--apply --json" -- "$cur") )
      else
        COMPREPLY=()
      fi
      ;;
    version)
      COMPREPLY=()
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
  local -a top mirror_sub ws_sub api_sub mcp_sub release_sub user_env_sub
  top=(mirror workspaces channels search docs completion api mcp release user-env version)
  api_sub=(serve)
  mcp_sub=(serve)
  release_sub=(check)
  user_env_sub=(install update rollback uninstall status validate-live check-live recover-live)
  mirror_sub=(init backfill embeddings-backfill process-embedding-jobs process-derived-text-jobs oauth-callback serve-webhooks serve-socket-mode process-events sync status daemon)
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
        '--client-id[Slack app client ID]:id:' \
        '--client-secret[Slack app client secret]:secret:' \
        '--bind[bind address]:address:' \
        '--port[port]:port:' \
        '--callback-path[oauth callback path]:path:' \
        '--redirect-uri[explicit redirect uri]:uri:' \
        '--cert-file[tls cert pem]:path:_files' \
        '--key-file[tls key pem]:path:_files' \
        '--scopes[bot scopes csv]:scopes:' \
        '--user-scopes[user scopes csv]:scopes:' \
        '--state[oauth state value]:state:' \
        '--timeout[oauth callback timeout seconds]:number:' \
        '--open-browser[open install URL in browser]' \
        '--limit[event limit]:number:' \
        '--loop[loop mode]' \
        '--interval[loop interval seconds]:number:' \
        '--max-cycles[max loop cycles]:number:' \
        '--stale-hours[stale threshold in hours]:number:' \
        '--healthy[emit HEALTHY or UNHEALTHY summary]' \
        '--fail-on-gap[exit 2 when any class exceeds thresholds]' \
        '--max-zero-msg[max zero-message channels before unhealthy]:number:' \
        '--max-stale[max stale channels before unhealthy]:number:' \
        '--enforce-stale[include stale threshold in health gate]' \
        '--classify-access[include A/B/C access classification]' \
        '--classify-limit[max zero-message channel ids per workspace]:number:' \
        '--json[json output]'
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
        _describe 'search command' '(keyword semantic derived-text corpus health query-dir reindex-keyword)'
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
        '--kind[derived-text kind filter]:kind:(attachment_text ocr_text)' \
        '--source-kind[derived-text source-kind filter]:source-kind:(file canvas)' \
        '--json[json output]'
      ;;
    completion)
      if (( CURRENT == 3 )); then
        _describe 'completion command' '(print)'
      elif (( CURRENT == 4 )); then
        _describe 'shell' '(bash zsh)'
      fi
      ;;
    api)
      if (( CURRENT == 3 )); then
        _describe 'api command' api_sub
        return
      fi
      _arguments '--bind[bind address]:address:' '--port[port]:port:'
      ;;
    mcp)
      if (( CURRENT == 3 )); then
        _describe 'mcp command' mcp_sub
        return
      fi
      _arguments
      ;;
    release)
      if (( CURRENT == 3 )); then
        _describe 'release command' release_sub
        return
      fi
      _arguments '--json[json output]' '--require-clean[fail when git worktree is dirty]' '--require-release-version[fail when version is still a development version]'
      ;;
    user-env)
      if (( CURRENT == 3 )); then
        _describe 'user-env command' user_env_sub
        return
      fi
      if [[ "$words[3]" == "uninstall" ]]; then
        _arguments '--purge-data[also remove config, DB, and cache]'
      elif [[ "$words[3]" == "status" || "$words[3]" == "validate-live" || "$words[3]" == "check-live" ]]; then
        _arguments '--json[json output]'
      elif [[ "$words[3]" == "recover-live" ]]; then
        _arguments '--apply[execute the safe remediations]' '--json[json output]'
      else
        _arguments
      fi
      ;;
    version)
      return
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


def cmd_version(args: argparse.Namespace) -> int:
    print(__version__)
    return 0


def cmd_release_check(args: argparse.Namespace) -> int:
    from slack_mirror.service.release import release_check

    return release_check(
        json_output=bool(args.json),
        require_clean=bool(args.require_clean),
        require_release_version=bool(args.require_release_version),
    )


def cmd_user_env_install(args: argparse.Namespace) -> int:
    from slack_mirror.service.user_env import install_user_env

    return install_user_env()


def cmd_user_env_update(args: argparse.Namespace) -> int:
    from slack_mirror.service.user_env import update_user_env

    return update_user_env()


def cmd_user_env_rollback(args: argparse.Namespace) -> int:
    from slack_mirror.service.user_env import rollback_user_env

    return rollback_user_env()


def cmd_user_env_uninstall(args: argparse.Namespace) -> int:
    from slack_mirror.service.user_env import uninstall_user_env

    return uninstall_user_env(purge_data=bool(args.purge_data))


def cmd_user_env_status(args: argparse.Namespace) -> int:
    from slack_mirror.service.user_env import status_user_env

    return status_user_env(json_output=bool(args.json))


def cmd_user_env_validate_live(args: argparse.Namespace) -> int:
    from slack_mirror.service.user_env import validate_live_user_env

    return validate_live_user_env(json_output=bool(args.json))


def cmd_user_env_check_live(args: argparse.Namespace) -> int:
    from slack_mirror.service.user_env import check_live_user_env

    return check_live_user_env(json_output=bool(args.json))


def cmd_user_env_recover_live(args: argparse.Namespace) -> int:
    from slack_mirror.service.user_env import recover_live_user_env

    return recover_live_user_env(apply=bool(args.apply), json_output=bool(args.json))


def cmd_serve_api(args: argparse.Namespace) -> int:
    from slack_mirror.service.api import run_api_server

    run_api_server(bind=args.bind, port=args.port, config_path=args.config)
    return 0


def cmd_serve_mcp(args: argparse.Namespace) -> int:
    from slack_mirror.service.mcp import run_mcp_stdio

    run_mcp_stdio(config_path=args.config)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slack-mirror",
        description="Slack workspace mirror CLI for backfills, webhook ingest, and processing.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--config",
        default=None,
        help="config path; if omitted, search ./config.local.yaml, ./config.yaml, then ~/.config/slack-mirror/config.yaml",
    )

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
    p_backfill.add_argument("--cache-root", default=None, help="override cache root (defaults to storage.cache_root from config)")
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

    p_derived_process = mirror_sub.add_parser("process-derived-text-jobs", help="process queued derived-text extraction jobs")
    p_derived_process.add_argument("--workspace", required=True, help="workspace name")
    p_derived_process.add_argument(
        "--kind",
        choices=["attachment_text", "ocr_text"],
        default="attachment_text",
        help="derived-text kind to process",
    )
    p_derived_process.add_argument("--limit", type=int, default=100, help="maximum jobs to process")
    p_derived_process.set_defaults(func=cmd_process_derived_text_jobs)

    p_oauth = mirror_sub.add_parser("oauth-callback", help="run local HTTPS Slack OAuth callback handler")
    p_oauth.add_argument("--workspace", required=True, help="workspace name from config")
    p_oauth.add_argument("--client-id", help="Slack app client ID (defaults to workspace config client_id)")
    p_oauth.add_argument("--client-secret", help="Slack app client secret (defaults to workspace config client_secret)")
    p_oauth.add_argument("--bind", default="localhost", help="HTTPS callback bind host")
    p_oauth.add_argument("--port", type=int, default=3000, help="HTTPS callback port")
    p_oauth.add_argument("--callback-path", default="/slack/oauth/callback", help="OAuth callback path")
    p_oauth.add_argument("--redirect-uri", help="explicit redirect URI (must match Slack app config)")
    p_oauth.add_argument("--cert-file", required=True, help="TLS cert PEM file (mkcert localhost cert)")
    p_oauth.add_argument("--key-file", required=True, help="TLS key PEM file (mkcert localhost key)")
    p_oauth.add_argument("--scopes", default="", help="comma-separated bot scopes")
    p_oauth.add_argument("--user-scopes", default="", help="comma-separated user scopes")
    p_oauth.add_argument("--state", help="optional OAuth state override")
    p_oauth.add_argument("--timeout", type=int, default=180, help="callback wait timeout in seconds")
    p_oauth.add_argument("--open-browser", action="store_true", help="open install URL automatically")
    p_oauth.set_defaults(func=cmd_mirror_oauth_callback)

    p_serve = mirror_sub.add_parser("serve-webhooks", help="run Slack events webhook receiver")
    p_serve.add_argument("--workspace", required=True)
    p_serve.add_argument("--bind")
    p_serve.add_argument("--port", type=int)
    p_serve.set_defaults(func=cmd_serve_webhooks)

    p_serve_socket = mirror_sub.add_parser("serve-socket-mode", help="run Slack events via Socket Mode")
    p_serve_socket.add_argument("--workspace", required=True)
    p_serve_socket.set_defaults(func=cmd_serve_socket_mode)

    p_process = mirror_sub.add_parser("process-events", help="process pending webhook events from DB")
    p_process.add_argument("--workspace", required=True)
    p_process.add_argument("--limit", type=int, default=100)
    p_process.add_argument("--loop", action="store_true")
    p_process.add_argument("--interval", type=float, default=2.0)
    p_process.add_argument("--max-cycles", type=int)
    p_process.set_defaults(func=cmd_process_events)

    p_sync = mirror_sub.add_parser("sync", help="run full reconcile sync (messages/threads + optional embeddings)")
    p_sync.add_argument("--workspace", help="optional workspace name (default: all workspaces)")
    p_sync.add_argument("--auth-mode", default="user", choices=["bot", "user"], help="auth mode for backfill")
    p_sync.add_argument("--include-files", action="store_true", help="include files/canvases metadata")
    p_sync.add_argument("--file-types", default="all", help="files.list types filter")
    p_sync.add_argument("--download-content", action="store_true", help="download file/canvas content")
    p_sync.add_argument("--cache-root", default=None, help="override cache root (defaults to storage.cache_root from config)")
    p_sync.add_argument("--messages-only", action="store_true", help="skip users/channels bootstrap and pull messages only")
    p_sync.add_argument("--channels", help="csv list of channel ids (messages-only mode)")
    p_sync.add_argument("--channel-limit", type=int, help="cap channels processed")
    p_sync.add_argument("--oldest", help="oldest message ts boundary (inclusive)")
    p_sync.add_argument("--latest", help="latest message ts boundary (inclusive)")
    p_sync.add_argument("--refresh-embeddings", action="store_true", help="enqueue and process embedding catch-up")
    p_sync.add_argument("--model", default="local-hash-128", help="embedding model id")
    p_sync.add_argument("--embedding-scan-limit", type=int, default=50000)
    p_sync.add_argument("--embedding-job-limit", type=int, default=5000)
    p_sync.add_argument("--reindex-keyword", action="store_true", help="rebuild FTS index after sync")
    p_sync.set_defaults(func=cmd_mirror_sync)

    p_status = mirror_sub.add_parser("status", help="show mirror coverage/freshness by workspace and channel class")
    p_status.add_argument("--workspace", help="optional workspace name")
    p_status.add_argument("--stale-hours", type=float, default=24.0, help="stale threshold in hours")
    p_status.add_argument("--healthy", action="store_true", help="emit HEALTHY/UNHEALTHY summary")
    p_status.add_argument("--fail-on-gap", action="store_true", help="exit code 2 when unhealthy")
    p_status.add_argument("--max-zero-msg", type=int, default=0, help="max zero-message channels allowed per row")
    p_status.add_argument("--max-stale", type=int, default=0, help="max stale channels allowed per row")
    p_status.add_argument("--enforce-stale", action="store_true", help="include stale threshold in health gate (default: observe stale but do not fail)")
    p_status.add_argument("--classify-access", action="store_true", help="include A/B/C access classification and C-bucket channel ids")
    p_status.add_argument("--classify-limit", type=int, default=200, help="max zero-message channel ids to print per workspace for classification")
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_mirror_status)

    p_daemon = mirror_sub.add_parser("daemon", help="unified event+embedding loop with periodic reconcile")
    p_daemon.add_argument("--workspace", help="optional workspace name (default: all workspaces)")
    p_daemon.add_argument("--interval", type=float, default=2.0, help="loop interval in seconds")
    p_daemon.add_argument("--event-limit", type=int, default=1000)
    p_daemon.add_argument("--embedding-limit", type=int, default=1000)
    p_daemon.add_argument("--model", default="local-hash-128", help="embedding model id")
    p_daemon.add_argument("--reconcile-minutes", type=float, default=30.0, help="periodic reconcile cadence (0 disables)")
    p_daemon.add_argument("--reconcile-channel-limit", type=int, default=300)
    p_daemon.add_argument("--auth-mode", default="user", choices=["bot", "user"], help="auth mode for reconcile backfill")
    p_daemon.add_argument("--cache-root", default=None, help="reserved for future file-cache reconcile support; defaults to storage.cache_root from config")
    p_daemon.add_argument("--max-cycles", type=int)
    p_daemon.set_defaults(func=cmd_mirror_daemon)

    workspaces = sub.add_parser("workspaces", help="workspace config/bootstrap/verification commands")
    ws_sub = workspaces.add_subparsers(dest="ws_cmd")
    p_ws_list = ws_sub.add_parser("list")
    p_ws_list.add_argument("--json", action="store_true")
    p_ws_list.set_defaults(func=cmd_workspaces_list)
    p_ws_sync = ws_sub.add_parser("sync-config")
    p_ws_sync.set_defaults(func=cmd_workspaces_sync)
    p_ws_verify = ws_sub.add_parser("verify")
    p_ws_verify.add_argument("--workspace")
    p_ws_verify.add_argument(
        "--require-explicit-outbound",
        action="store_true",
        help="fail when outbound_token/outbound_user_token are not explicitly configured",
    )
    p_ws_verify.set_defaults(func=cmd_workspaces_verify)

    channels = sub.add_parser("channels", help="channel mapping integration helpers")
    channels_sub = channels.add_subparsers(dest="channels_cmd")
    p_sync = channels_sub.add_parser("sync-from-tool")
    p_sync.add_argument("--json", action="store_true")
    p_sync.set_defaults(func=cmd_channels_sync_from_tool)

    messages = sub.add_parser("messages", help="raw message retrieval commands")
    messages_sub = messages.add_subparsers(dest="messages_cmd")
    p_messages_list = messages_sub.add_parser("list", help="list messages in a time window")
    p_messages_list.add_argument("--workspace", required=True, help="workspace name")
    p_messages_list.add_argument("--after", help="minimum timestamp (inclusive)")
    p_messages_list.add_argument("--before", help="maximum timestamp (inclusive)")
    p_messages_list.add_argument("--channels", help="comma-separated list of channel IDs or names")
    p_messages_list.add_argument("--limit", type=int, default=1000, help="maximum results")
    p_messages_list.add_argument("--json", action="store_true")
    p_messages_list.set_defaults(func=cmd_messages_list)

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

    p_search_derived = search_sub.add_parser("derived-text", help="search extracted attachment, canvas, and OCR text")
    p_search_derived.add_argument("--workspace", required=True, help="workspace name")
    p_search_derived.add_argument("--query", required=True, help="query text")
    p_search_derived.add_argument("--limit", type=int, default=20, help="maximum result rows")
    p_search_derived.add_argument(
        "--kind",
        choices=["attachment_text", "ocr_text"],
        default=None,
        help="optional derived-text kind filter",
    )
    p_search_derived.add_argument(
        "--source-kind",
        choices=["file", "canvas"],
        default=None,
        help="optional source kind filter",
    )
    p_search_derived.add_argument("--json", action="store_true", help="json output")
    p_search_derived.set_defaults(func=cmd_search_derived_text)

    p_search_corpus = search_sub.add_parser("corpus", help="search messages plus derived attachment and OCR text")
    p_search_scope = p_search_corpus.add_mutually_exclusive_group(required=True)
    p_search_scope.add_argument("--workspace", help="workspace name")
    p_search_scope.add_argument("--all-workspaces", action="store_true", help="search across all enabled workspaces")
    p_search_corpus.add_argument("--query", required=True, help="query text")
    p_search_corpus.add_argument("--limit", type=int, default=20, help="maximum result rows")
    p_search_corpus.add_argument("--mode", choices=["lexical", "semantic", "hybrid"], default=None, help="corpus retrieval mode")
    p_search_corpus.add_argument("--model", default=None, help="embedding model id")
    p_search_corpus.add_argument("--lexical-weight", type=float, default=None, help="hybrid lexical score weight")
    p_search_corpus.add_argument("--semantic-weight", type=float, default=None, help="hybrid semantic score weight")
    p_search_corpus.add_argument("--semantic-scale", type=float, default=None, help="semantic score scaling factor")
    p_search_corpus.add_argument("--no-fts", action="store_true", help="disable FTS prefilter for message lexical search")
    p_search_corpus.add_argument(
        "--kind",
        choices=["attachment_text", "ocr_text"],
        default=None,
        help="optional derived-text kind filter",
    )
    p_search_corpus.add_argument(
        "--source-kind",
        choices=["file", "canvas"],
        default=None,
        help="optional derived-text source kind filter",
    )
    p_search_corpus.add_argument("--explain", action="store_true", help="include score breakdown")
    p_search_corpus.add_argument("--json", action="store_true", help="json output")
    p_search_corpus.set_defaults(func=cmd_search_corpus)

    p_search_health = search_sub.add_parser("health", help="show search readiness and optional benchmark health")
    p_search_health.add_argument("--workspace", required=True, help="workspace name")
    p_search_health.add_argument("--dataset", help="optional JSONL benchmark dataset path")
    p_search_health.add_argument("--mode", choices=["lexical", "semantic", "hybrid"], default="hybrid", help="benchmark retrieval mode")
    p_search_health.add_argument("--limit", type=int, default=10, help="benchmark result window")
    p_search_health.add_argument("--model", default="local-hash-128", help="embedding model id for benchmark mode")
    p_search_health.add_argument("--min-hit-at-3", type=float, default=0.5, help="minimum acceptable hit@3 when dataset is provided")
    p_search_health.add_argument("--min-hit-at-10", type=float, default=0.8, help="minimum acceptable hit@10 when dataset is provided")
    p_search_health.add_argument("--min-ndcg-at-k", type=float, default=0.6, help="minimum acceptable ndcg@k when dataset is provided")
    p_search_health.add_argument("--max-latency-p95-ms", type=float, default=800.0, help="maximum acceptable benchmark latency p95")
    p_search_health.add_argument("--json", action="store_true", help="json output")
    p_search_health.set_defaults(func=cmd_search_health)

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

    api = sub.add_parser("api", help="local HTTP API commands")
    api_sub = api.add_subparsers(dest="api_cmd")
    p_api_serve = api_sub.add_parser("serve", help="run the local HTTP API server")
    p_api_serve.add_argument("--bind", default="127.0.0.1", help="bind address")
    p_api_serve.add_argument("--port", type=int, default=8788, help="listen port")
    p_api_serve.set_defaults(func=cmd_serve_api)

    mcp = sub.add_parser("mcp", help="local MCP server commands")
    mcp_sub = mcp.add_subparsers(dest="mcp_cmd")
    p_mcp_serve = mcp_sub.add_parser("serve", help="run the local MCP stdio server")
    p_mcp_serve.set_defaults(func=cmd_serve_mcp)

    release = sub.add_parser("release", help="release-discipline validation commands")
    release_sub = release.add_subparsers(dest="release_cmd")
    p_release_check = release_sub.add_parser("check", help="run the supported release-readiness checks")
    p_release_check.add_argument("--json", action="store_true", help="json output")
    p_release_check.add_argument("--require-clean", action="store_true", help="fail when git worktree is dirty")
    p_release_check.add_argument(
        "--require-release-version",
        action="store_true",
        help="fail when pyproject version is still a development version",
    )
    p_release_check.set_defaults(func=cmd_release_check)

    user_env = sub.add_parser("user-env", help="supported user-scope install/update commands")
    user_env_sub = user_env.add_subparsers(dest="user_env_cmd")
    p_user_install = user_env_sub.add_parser("install", help="install isolated user runtime from the current repo")
    p_user_install.set_defaults(func=cmd_user_env_install)
    p_user_update = user_env_sub.add_parser("update", help="update isolated user runtime from the current repo")
    p_user_update.set_defaults(func=cmd_user_env_update)
    p_user_rollback = user_env_sub.add_parser(
        "rollback",
        help="restore the previous managed app snapshot without rolling back DB schema",
    )
    p_user_rollback.set_defaults(func=cmd_user_env_rollback)
    p_user_uninstall = user_env_sub.add_parser("uninstall", help="remove isolated user runtime")
    p_user_uninstall.add_argument("--purge-data", action="store_true", help="also remove config, DB, and cache")
    p_user_uninstall.set_defaults(func=cmd_user_env_uninstall)
    p_user_status = user_env_sub.add_parser("status", help="show user-scope install status")
    p_user_status.add_argument("--json", action="store_true", help="json output")
    p_user_status.set_defaults(func=cmd_user_env_status)
    p_user_validate_live = user_env_sub.add_parser(
        "validate-live",
        help="validate the supported live-service contract for the managed user environment",
    )
    p_user_validate_live.add_argument("--json", action="store_true", help="json output")
    p_user_validate_live.set_defaults(func=cmd_user_env_validate_live)
    p_user_check_live = user_env_sub.add_parser(
        "check-live",
        help="run one operator smoke check over managed runtime artifacts and live-service validation",
    )
    p_user_check_live.add_argument("--json", action="store_true", help="json output")
    p_user_check_live.set_defaults(func=cmd_user_env_check_live)
    p_user_recover_live = user_env_sub.add_parser(
        "recover-live",
        help="plan or apply only the bounded safe remediations for a failing live runtime",
    )
    p_user_recover_live.add_argument("--apply", action="store_true", help="execute the safe remediations")
    p_user_recover_live.add_argument("--json", action="store_true", help="json output")
    p_user_recover_live.set_defaults(func=cmd_user_env_recover_live)

    version_parser = sub.add_parser("version", help="print the package version")
    version_parser.set_defaults(func=cmd_version)

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
