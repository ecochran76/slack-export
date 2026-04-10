from __future__ import annotations

from slack_sdk.errors import SlackApiError

from pathlib import Path

from slack_mirror.core.db import (
    get_sync_state,
    list_channel_ids,
    list_recent_thread_roots,
    set_sync_state,
    update_file_download,
    upsert_canvas,
    upsert_channel,
    upsert_file,
    upsert_message,
    upsert_user,
)


RECENT_THREAD_ROOT_LOOKBACK_SECONDS = 48 * 3600
from slack_mirror.core.slack_api import SlackApiClient
from slack_mirror.sync.downloads import download_with_retries


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
    *,
    token: str,
    workspace_id: int,
    conn,
    channel_limit: int | None = None,
    oldest: str | None = None,
    latest: str | None = None,
    channel_ids_override: list[str] | None = None,
) -> dict[str, int]:
    api = SlackApiClient(token)
    channel_ids = channel_ids_override[:] if channel_ids_override else list_channel_ids(conn, workspace_id)
    if channel_limit:
        channel_ids = channel_ids[:channel_limit]

    total_messages = 0
    processed_channels = 0
    skipped_channels = 0
    for channel_id in channel_ids:
        checkpoint_key = f"messages.oldest.{channel_id}"
        effective_oldest = oldest if oldest is not None else (get_sync_state(conn, workspace_id, checkpoint_key) or "0")
        try:
            messages = api.conversation_history(channel_id=channel_id, oldest=effective_oldest, latest=latest)
        except SlackApiError as exc:
            if exc.response.get("error") in {"not_in_channel", "missing_scope", "channel_not_found"}:
                skipped_channels += 1
                continue
            raise
        for msg in messages:
            upsert_message(conn, workspace_id, channel_id, msg)

        # Thread completeness: pull replies for roots in the current history slice,
        # plus recently known thread roots from the DB. This closes a blind spot where
        # a quiet channel can have new replies on an older thread root that never
        # appears in the incremental conversations.history window.
        reply_roots = {
            str(m.get("ts"))
            for m in messages
            if m.get("ts") and int(m.get("reply_count") or 0) > 0
        }
        try:
            effective_oldest_f = float(effective_oldest or "0")
        except ValueError:
            effective_oldest_f = 0.0
        if effective_oldest_f > 0:
            recent_root_cutoff = max(0.0, effective_oldest_f - RECENT_THREAD_ROOT_LOOKBACK_SECONDS)
            reply_roots.update(
                list_recent_thread_roots(
                    conn,
                    workspace_id,
                    channel_id,
                    min_ts=str(recent_root_cutoff),
                )
            )

        thread_reply_count = 0
        newest_seen_ts: float | None = None
        for msg in messages:
            try:
                newest_seen_ts = max(newest_seen_ts or 0.0, float(str(msg.get("ts") or "0")))
            except ValueError:
                continue
        for thread_ts in sorted(reply_roots):
            try:
                replies = api.conversation_replies(
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    oldest=effective_oldest,
                    latest=latest,
                )
            except SlackApiError as exc:
                if exc.response.get("error") in {"not_in_channel", "missing_scope", "channel_not_found", "thread_not_found"}:
                    continue
                raise
            for r in replies:
                upsert_message(conn, workspace_id, channel_id, r)
                try:
                    newest_seen_ts = max(newest_seen_ts or 0.0, float(str(r.get("ts") or "0")))
                except ValueError:
                    continue
            thread_reply_count += len(replies)

        total_messages += len(messages) + thread_reply_count
        processed_channels += 1
        if newest_seen_ts is not None and oldest is None and latest is None:
            set_sync_state(conn, workspace_id, checkpoint_key, str(newest_seen_ts))

    return {"channels": processed_channels, "messages": total_messages, "skipped": skipped_channels}


def _safe_name(value: str, fallback: str) -> str:
    name = (value or fallback).strip()
    return "".join(c for c in name if c.isalnum() or c in ("-", "_", ".")) or fallback


def backfill_files_and_canvases(
    *,
    token: str,
    workspace_id: int,
    conn,
    cache_root: str = "./cache",
    download_content: bool = False,
    file_types: str = "images,snippets,gdocs,zips,pdfs",
) -> dict[str, int]:
    api = SlackApiClient(token)

    normalized_types = (file_types or "").strip().lower()
    file_types_arg = None if normalized_types in {"", "all", "*"} else file_types

    files = api.list_files(types=file_types_arg)
    canvases = api.list_files(types="canvas")
    canvas_ids = {c.get("id") for c in canvases if c.get("id")}
    if canvas_ids:
        files = [f for f in files if f.get("id") not in canvas_ids]

    files_dir = Path(cache_root) / "files"
    canvases_dir = Path(cache_root) / "canvases"
    files_dir.mkdir(parents=True, exist_ok=True)
    canvases_dir.mkdir(parents=True, exist_ok=True)

    file_count = 0
    file_downloaded = 0
    canvas_count = 0
    canvas_downloaded = 0

    for f in files:
        fid = f.get("id")
        if not fid:
            continue
        local = files_dir / fid / _safe_name(f.get("name") or f.get("title") or fid, f"file_{fid}")
        local.parent.mkdir(parents=True, exist_ok=True)
        upsert_file(conn, workspace_id, f, local_path=str(local))

        if download_content and f.get("url_private_download"):
            ok, checksum_or_error = download_with_retries(f["url_private_download"], token, local)
            if ok and checksum_or_error:
                update_file_download(conn, workspace_id, fid, str(local), checksum_or_error)
                file_downloaded += 1
        file_count += 1

    for c in canvases:
        cid = c.get("id")
        if not cid:
            continue
        local = canvases_dir / f"{cid}.html"
        upsert_canvas(conn, workspace_id, c, local_path=str(local))

        if download_content and c.get("url_private_download"):
            ok, _ = download_with_retries(c["url_private_download"], token, local)
            if ok:
                canvas_downloaded += 1
        canvas_count += 1

    return {
        "files": file_count,
        "canvases": canvas_count,
        "files_downloaded": file_downloaded,
        "canvases_downloaded": canvas_downloaded,
    }
