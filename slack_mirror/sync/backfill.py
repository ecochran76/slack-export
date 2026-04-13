from __future__ import annotations

import html
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from slack_sdk.errors import SlackApiError

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
from slack_mirror.sync.downloads import classify_download_error, download_with_retries, sha256_file


class _EmailAssetUrlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key not in {"src", "href"}:
                continue
            if not isinstance(value, str) or "files-email-priv" not in value:
                continue
            if value not in self.urls:
                self.urls.append(value)


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


def _planned_file_path(*, cache_root: str, file_obj: dict[str, object]) -> Path | None:
    fid = file_obj.get("id")
    if not fid:
        return None
    return Path(cache_root) / "files" / str(fid) / _safe_name(
        str(file_obj.get("name") or file_obj.get("title") or fid),
        f"file_{fid}",
    )


def _planned_email_path(*, cache_root: str, file_obj: dict[str, object]) -> Path | None:
    local = _planned_file_path(cache_root=cache_root, file_obj=file_obj)
    if local is None:
        return None
    if local.suffix.lower() not in {".html", ".htm"}:
        return local.with_suffix(".html")
    return local


def _looks_like_html_payload(content: bytes, content_type: str | None) -> bool:
    lowered = (content[:512] or b"").lstrip().lower()
    ctype = str(content_type or "").lower()
    return "text/html" in ctype or lowered.startswith(b"<!doctype html") or lowered.startswith(b"<html")


def _download_email_inline_asset(*, url: str, token: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60) as resp:
        resp.raise_for_status()
        content = resp.content
        if _looks_like_html_payload(content, resp.headers.get("Content-Type")):
            return False
        dest.write_bytes(content)
    return True


def _materialize_email_container(
    *,
    token: str,
    cache_root: str,
    file_obj: dict[str, object],
) -> tuple[bool, str | None, str | None]:
    preview_html = file_obj.get("preview") or file_obj.get("simplified_html")
    plain_text = file_obj.get("preview_plain_text") or file_obj.get("plain_text")
    if isinstance(preview_html, str) and preview_html.strip():
        body = str(preview_html)
    elif isinstance(plain_text, str) and plain_text.strip():
        body = f"<pre>{html.escape(str(plain_text))}</pre>"
    else:
        return False, None, "email container missing preview content"

    html_path = _planned_email_path(cache_root=cache_root, file_obj=file_obj)
    if html_path is None:
        return False, None, "email container missing file id"
    html_path.parent.mkdir(parents=True, exist_ok=True)

    parser = _EmailAssetUrlParser()
    parser.feed(body)
    if parser.urls:
        asset_dir = html_path.parent / f"{html_path.stem}_assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        for index, url in enumerate(parser.urls, start=1):
            parsed = urlparse(url)
            asset_name = Path(unquote(parsed.path)).name or f"asset_{index}"
            asset_dest = asset_dir / _safe_name(asset_name, f"asset_{index}")
            try:
                if _download_email_inline_asset(url=url, token=token, dest=asset_dest):
                    body = body.replace(url, f"{asset_dir.name}/{asset_dest.name}")
            except Exception:
                continue

    title = str(file_obj.get("title") or file_obj.get("name") or file_obj.get("id") or "email")
    html_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "</head><body>"
        f"{body}"
        "</body></html>",
        encoding="utf-8",
    )
    return True, str(html_path), sha256_file(html_path)


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
        local = _planned_file_path(cache_root=cache_root, file_obj=f)
        if local is None:
            continue
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


def reconcile_file_downloads(
    *,
    token: str,
    workspace_id: int,
    conn,
    cache_root: str = "./cache",
    limit: int = 100,
) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT file_id, raw_json, local_path
        FROM files
        WHERE workspace_id = ?
          AND raw_json IS NOT NULL
          AND raw_json LIKE '%url_private_download%'
        ORDER BY updated_at ASC, file_id ASC
        """,
        (workspace_id,),
    ).fetchall()

    scanned = 0
    attempted = 0
    downloaded = 0
    downloaded_binary = 0
    materialized_email_containers = 0
    skipped = 0
    failed = 0
    failure_reasons: dict[str, int] = {}
    failed_files: list[dict[str, str]] = []

    def classify_reconcile_failure(file_obj: dict[str, object], error: str | None) -> str:
        base = classify_download_error(error)
        mode = str(file_obj.get("mode") or "").strip().lower()
        mimetype = str(file_obj.get("mimetype") or "").strip().lower()
        attachment_count = int(file_obj.get("original_attachment_count") or 0)
        if mode == "email" and mimetype == "text/html":
            return "email_container_with_attachments" if attachment_count > 0 else "email_container"
        return base

    for row in rows:
        scanned += 1
        raw_json = row["raw_json"]
        if not raw_json:
            skipped += 1
            continue
        try:
            file_obj = json.loads(raw_json)
        except Exception:
            failed += 1
            continue

        download_url = str(file_obj.get("url_private_download") or "").strip()
        if not download_url:
            skipped += 1
            continue

        existing_local_path = str(row["local_path"] or "").strip()
        if existing_local_path and Path(existing_local_path).exists():
            skipped += 1
            continue

        if attempted >= limit:
            break

        attempted += 1
        mode = str(file_obj.get("mode") or "").strip().lower()
        mimetype = str(file_obj.get("mimetype") or "").strip().lower()
        if mode == "email" and mimetype == "text/html":
            ok, local_path, checksum_or_error = _materialize_email_container(
                token=token,
                cache_root=cache_root,
                file_obj=file_obj,
            )
        else:
            local = _planned_file_path(cache_root=cache_root, file_obj=file_obj)
            if local is None:
                failed += 1
                continue
            local.parent.mkdir(parents=True, exist_ok=True)
            ok, checksum_or_error = download_with_retries(download_url, token, local)
            local_path = str(local) if ok else None

        if ok and checksum_or_error and local_path:
            update_file_download(conn, workspace_id, str(file_obj.get("id") or row["file_id"]), local_path, checksum_or_error)
            downloaded += 1
            if mode == "email" and mimetype == "text/html":
                materialized_email_containers += 1
            else:
                downloaded_binary += 1
        else:
            failed += 1
            reason = classify_reconcile_failure(file_obj, checksum_or_error)
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
            failed_files.append(
                {
                    "file_id": str(file_obj.get("id") or row["file_id"]),
                    "name": str(file_obj.get("name") or file_obj.get("title") or row["file_id"]),
                    "reason": reason,
                    "error": str(checksum_or_error or ""),
                }
            )

    return {
        "scanned": scanned,
        "attempted": attempted,
        "downloaded": downloaded,
        "downloaded_binary": downloaded_binary,
        "materialized_email_containers": materialized_email_containers,
        "skipped": skipped,
        "failed": failed,
        "failure_reasons": failure_reasons,
        "failed_files": failed_files,
    }
