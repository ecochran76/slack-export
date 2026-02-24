from __future__ import annotations

import argparse
import json
from pathlib import Path

from slack_mirror.core.config import load_config
from slack_mirror.core.db import (
    apply_migrations,
    connect,
    get_workspace_by_name,
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
    from slack_mirror.sync.backfill import backfill_messages, backfill_users_and_channels

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
        )
    print(
        "Backfill complete "
        f"workspace={ws_cfg.get('name')} users={counts['users']} channels={counts['channels']} "
        f"message_channels={message_counts['channels']} messages={message_counts['messages']} "
        f"skipped_channels={message_counts['skipped']}"
    )
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


def cmd_docs_generate(_: argparse.Namespace) -> int:
    print("TODO: wire automatic CLI docs generation")
    return 0


def cmd_completion(args: argparse.Namespace) -> int:
    shell = args.shell
    if shell == "bash":
        print("# TODO: emit dynamic bash completion script")
    elif shell == "zsh":
        print("# TODO: emit dynamic zsh completion script")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="slack-mirror")
    parser.add_argument("--config", default="config.yaml")

    sub = parser.add_subparsers(dest="command")

    mirror = sub.add_parser("mirror")
    mirror_sub = mirror.add_subparsers(dest="mirror_cmd")
    p_init = mirror_sub.add_parser("init")
    p_init.set_defaults(func=cmd_mirror_init)
    p_backfill = mirror_sub.add_parser("backfill")
    p_backfill.add_argument("--workspace", required=True)
    p_backfill.add_argument("--include-messages", action="store_true")
    p_backfill.add_argument("--channel-limit", type=int)
    p_backfill.set_defaults(func=cmd_mirror_backfill)

    workspaces = sub.add_parser("workspaces")
    ws_sub = workspaces.add_subparsers(dest="ws_cmd")
    p_ws_list = ws_sub.add_parser("list")
    p_ws_list.add_argument("--json", action="store_true")
    p_ws_list.set_defaults(func=cmd_workspaces_list)
    p_ws_sync = ws_sub.add_parser("sync-config")
    p_ws_sync.set_defaults(func=cmd_workspaces_sync)
    p_ws_verify = ws_sub.add_parser("verify")
    p_ws_verify.add_argument("--workspace")
    p_ws_verify.set_defaults(func=cmd_workspaces_verify)

    channels = sub.add_parser("channels")
    channels_sub = channels.add_subparsers(dest="channels_cmd")
    p_sync = channels_sub.add_parser("sync-from-tool")
    p_sync.add_argument("--json", action="store_true")
    p_sync.set_defaults(func=cmd_channels_sync_from_tool)

    docs = sub.add_parser("docs")
    docs_sub = docs.add_subparsers(dest="docs_cmd")
    p_docs = docs_sub.add_parser("generate")
    p_docs.set_defaults(func=cmd_docs_generate)

    completion = sub.add_parser("completion")
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
