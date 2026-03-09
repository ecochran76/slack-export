#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from slack_sdk.errors import SlackApiError

from slack_mirror.core.config import load_config
from slack_mirror.core.db import apply_migrations, connect, get_workspace_by_name, upsert_workspace
from slack_mirror.sync.backfill import backfill_messages, backfill_users_and_channels
from slack_mirror.sync.embeddings import process_embedding_jobs

MIGRATIONS_DIR = str(Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations")
DEFAULT_STATE = Path(".local/state/catchup_state.json")


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"workspaces": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def ensure_workspace(conn: sqlite3.Connection, cfg: dict[str, Any], workspace: str) -> tuple[int, dict[str, Any]]:
    ws_cfg = next(w for w in cfg.get("workspaces", []) if w.get("name") == workspace)
    row = get_workspace_by_name(conn, workspace)
    if row:
        return int(row["id"]), ws_cfg
    workspace_id = upsert_workspace(
        conn,
        name=ws_cfg.get("name", workspace),
        team_id=ws_cfg.get("team_id"),
        domain=ws_cfg.get("domain"),
        config=ws_cfg,
    )
    return workspace_id, ws_cfg


def list_candidate_channels(conn: sqlite3.Connection, workspace_id: int, stale_before_ts: float) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          c.channel_id,
          COALESCE(c.name, c.channel_id) AS channel_name,
          COUNT(m.ts) AS msg_count,
          MAX(CAST(m.ts AS REAL)) AS latest_ts,
          MAX(CAST(ss.value AS REAL)) AS checkpoint_ts
        FROM channels c
        LEFT JOIN messages m
          ON m.workspace_id = c.workspace_id AND m.channel_id = c.channel_id
        LEFT JOIN sync_state ss
          ON ss.workspace_id = c.workspace_id AND ss.key = ('messages.oldest.' || c.channel_id)
        WHERE c.workspace_id = ?
        GROUP BY c.channel_id, c.name
        ORDER BY
          CASE WHEN MAX(CAST(m.ts AS REAL)) IS NULL THEN 0 ELSE 1 END,
          COALESCE(MAX(CAST(m.ts AS REAL)), 0) ASC,
          c.channel_id ASC
        """,
        (workspace_id,),
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        latest_ts = row["latest_ts"]
        checkpoint_ts = row["checkpoint_ts"]
        msg_count = int(row["msg_count"] or 0)
        needs_catchup = (
            msg_count == 0
            or latest_ts is None
            or float(latest_ts) < stale_before_ts
            or checkpoint_ts is None
        )
        if needs_catchup:
            items.append(
                {
                    "channel_id": row["channel_id"],
                    "channel_name": row["channel_name"],
                    "msg_count": msg_count,
                    "latest_ts": float(latest_ts) if latest_ts is not None else None,
                    "checkpoint_ts": float(checkpoint_ts) if checkpoint_ts is not None else None,
                }
            )
    return items


def process_workspace(
    *,
    conn: sqlite3.Connection,
    cfg: dict[str, Any],
    workspace: str,
    stale_hours: float,
    embedding_limit: int,
    state: dict[str, Any],
    per_pass_limit: int | None,
) -> dict[str, Any]:
    workspace_id, ws_cfg = ensure_workspace(conn, cfg, workspace)
    token = ws_cfg.get("user_token") or ws_cfg.get("token")
    if not token:
        raise ValueError(f"Workspace '{workspace}' has no token configured")

    backfill_users_and_channels(token=token, workspace_id=workspace_id, conn=conn)

    stale_before_ts = time.time() - stale_hours * 3600
    candidates = list_candidate_channels(conn, workspace_id, stale_before_ts)
    if per_pass_limit:
        candidates = candidates[:per_pass_limit]

    ws_state = state.setdefault("workspaces", {}).setdefault(workspace, {"channels": {}, "passes": 0})
    ws_state["passes"] = int(ws_state.get("passes", 0)) + 1

    processed = 0
    skipped = 0
    for item in candidates:
        channel_id = item["channel_id"]
        channel_name = item["channel_name"]
        try:
            stats = backfill_messages(
                token=token,
                workspace_id=workspace_id,
                conn=conn,
                channel_ids_override=[channel_id],
            )
            process_embedding_jobs(conn, workspace_id=workspace_id, model_id="local-hash-128", limit=embedding_limit)
            ws_state["channels"][channel_id] = {
                "channel_name": channel_name,
                "last_attempt": time.time(),
                "status": "ok",
                "stats": stats,
            }
            processed += 1
            print(
                f"[catchup] workspace={workspace} channel={channel_name}({channel_id}) "
                f"messages={stats['messages']} skipped={stats['skipped']}"
            )
        except SlackApiError as exc:
            err = exc.response.get("error", "unknown")
            ws_state["channels"][channel_id] = {
                "channel_name": channel_name,
                "last_attempt": time.time(),
                "status": f"slack_error:{err}",
            }
            if err in {"not_in_channel", "missing_scope", "channel_not_found"}:
                skipped += 1
                print(f"[catchup] workspace={workspace} channel={channel_name}({channel_id}) skipped error={err}")
                continue
            raise
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            ws_state["channels"][channel_id] = {
                "channel_name": channel_name,
                "last_attempt": time.time(),
                "status": "db_locked",
            }
            print(f"[catchup] workspace={workspace} channel={channel_name}({channel_id}) deferred reason=db_locked")
            time.sleep(2.0)

    remaining = len(list_candidate_channels(conn, workspace_id, stale_before_ts))
    summary = {
        "workspace": workspace,
        "processed": processed,
        "skipped": skipped,
        "remaining": remaining,
        "pass_candidates": len(candidates),
    }
    print(
        f"[catchup] workspace={workspace} pass_complete processed={processed} skipped={skipped} remaining={remaining}"
    )
    return summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rate-limit-aware Slack catch-up runner")
    p.add_argument("--config", default="config.local.yaml")
    p.add_argument("--workspace", action="append", dest="workspaces", help="workspace to process (repeatable)")
    p.add_argument("--stale-hours", type=float, default=24.0)
    p.add_argument("--embedding-limit", type=int, default=500)
    p.add_argument("--state-file", default=str(DEFAULT_STATE))
    p.add_argument("--sleep-seconds", type=float, default=30.0, help="sleep between full passes when work remains")
    p.add_argument("--max-passes", type=int, default=0, help="0 means run until clean")
    p.add_argument("--per-pass-limit", type=int, default=50, help="max candidate channels per workspace per pass")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config).data
    db_path = cfg.get("storage", {}).get("db_path", "./data/slack_mirror.db")
    conn = connect(db_path)
    conn.execute("PRAGMA busy_timeout = 5000")
    apply_migrations(conn, MIGRATIONS_DIR)

    state_path = Path(args.state_file)
    state = load_state(state_path)
    workspaces = args.workspaces or [w.get("name") for w in cfg.get("workspaces", []) if w.get("enabled", True)]

    passes = 0
    while True:
        passes += 1
        save_state(state_path, state)
        summaries = [
            process_workspace(
                conn=conn,
                cfg=cfg,
                workspace=ws,
                stale_hours=args.stale_hours,
                embedding_limit=args.embedding_limit,
                state=state,
                per_pass_limit=args.per_pass_limit,
            )
            for ws in workspaces
        ]
        save_state(state_path, state)

        total_remaining = sum(item["remaining"] for item in summaries)
        if total_remaining == 0:
            print("[catchup] complete")
            return 0
        if args.max_passes and passes >= args.max_passes:
            print(f"[catchup] stopping after max passes={args.max_passes} remaining={total_remaining}")
            return 0
        print(f"[catchup] sleeping seconds={args.sleep_seconds} remaining={total_remaining}")
        time.sleep(args.sleep_seconds)


if __name__ == "__main__":
    sys.exit(main())
