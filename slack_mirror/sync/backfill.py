from __future__ import annotations

from slack_sdk.errors import SlackApiError

from pathlib import Path

from slack_mirror.core.db import (
    get_sync_state,
    list_channel_ids,
    set_sync_state,
    upsert_canvas,
    upsert_channel,
    upsert_file,
    upsert_message,
    upsert_user,
)
from slack_mirror.core.slack_api import SlackApiClient


def backfill_users_and_channels(*, token: str, workspace_id: int, conn) -> dict[str, int]:
    api = SlackApiClient(token)

    users = api.list_users()
    for user in users:
        if not user.get("id"):
            continue
        upsert_user(conn, workspace_id, user)

    channels = api.list_conversations()
    for channel in channels:
        if not channel.get("id"):
            continue
        upsert_channel(conn, workspace_id, channel)

    return {"users": len(users), "channels": len(channels)}


def backfill_messages(
    *, token: str, workspace_id: int, conn, channel_limit: int | None = None
) -> dict[str, int]:
    api = SlackApiClient(token)
    channel_ids = list_channel_ids(conn, workspace_id)
    if channel_limit:
        channel_ids = channel_ids[:channel_limit]

    total_messages = 0
    processed_channels = 0
    skipped_channels = 0
    for channel_id in channel_ids:
        checkpoint_key = f"messages.oldest.{channel_id}"
        oldest = get_sync_state(conn, workspace_id, checkpoint_key) or "0"
        try:
            messages = api.conversation_history(channel_id=channel_id, oldest=oldest)
        except SlackApiError as exc:
            if exc.response.get("error") in {"not_in_channel", "missing_scope", "channel_not_found"}:
                skipped_channels += 1
                continue
            raise
        for msg in messages:
            upsert_message(conn, workspace_id, channel_id, msg)
        total_messages += len(messages)
        processed_channels += 1
        if messages:
            newest_ts = max(str(m.get("ts", "0")) for m in messages)
            set_sync_state(conn, workspace_id, checkpoint_key, newest_ts)

    return {"channels": processed_channels, "messages": total_messages, "skipped": skipped_channels}


def _safe_name(value: str, fallback: str) -> str:
    name = (value or fallback).strip()
    return "".join(c for c in name if c.isalnum() or c in ("-", "_", ".")) or fallback


def backfill_files_and_canvases(
    *, token: str, workspace_id: int, conn, cache_root: str = "./cache"
) -> dict[str, int]:
    api = SlackApiClient(token)

    files = api.list_files(types="images,snippets,gdocs,zips,pdfs")
    canvases = api.list_files(types="canvas")

    files_dir = Path(cache_root) / "files"
    canvases_dir = Path(cache_root) / "canvases"
    files_dir.mkdir(parents=True, exist_ok=True)
    canvases_dir.mkdir(parents=True, exist_ok=True)

    file_count = 0
    for f in files:
        fid = f.get("id")
        if not fid:
            continue
        local = files_dir / fid / _safe_name(f.get("name") or f.get("title") or fid, f"file_{fid}")
        local.parent.mkdir(parents=True, exist_ok=True)
        upsert_file(conn, workspace_id, f, local_path=str(local))
        file_count += 1

    canvas_count = 0
    for c in canvases:
        cid = c.get("id")
        if not cid:
            continue
        local = canvases_dir / f"{cid}.html"
        upsert_canvas(conn, workspace_id, c, local_path=str(local))
        canvas_count += 1

    return {"files": file_count, "canvases": canvas_count}
