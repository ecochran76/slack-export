from __future__ import annotations

import json
import time
from typing import Any
from datetime import UTC, datetime

from slack_mirror.core.db import (
    append_child_event,
    mark_event_status,
    remove_channel_member,
    upsert_channel,
    upsert_channel_member,
    upsert_file,
    upsert_message,
)


def _event_time_to_iso(value: Any) -> str | None:
    try:
        numeric = float(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(numeric, tz=UTC).isoformat().replace("+00:00", "Z")


def _raw_event_id(payload: dict[str, Any], fallback: str) -> str:
    return str(payload.get("event_id") or fallback or "").strip()


def _record_child_event(
    conn,
    workspace_id: int,
    payload: dict[str, Any],
    *,
    event_type: str,
    subject_kind: str,
    subject_id: str,
    raw_suffix: str,
    actor_user_id: str | None = None,
    actor_label: str | None = None,
    channel_id: str | None = None,
    source_refs: dict[str, Any] | None = None,
    event_payload: dict[str, Any] | None = None,
) -> None:
    raw_id = _raw_event_id(payload, raw_suffix)
    workspace_row = conn.execute("SELECT name FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    workspace_name = str(workspace_row["name"] or "") if workspace_row else ""
    stable_subject_id = subject_id
    if workspace_name and subject_id.startswith("message|"):
        parts = subject_id.split("|")
        if len(parts) == 3:
            stable_subject_id = f"message|{workspace_name}|{parts[1]}|{parts[2]}"
    append_child_event(
        conn,
        workspace_id=workspace_id,
        event_id=f"{event_type}|{raw_id}",
        event_type=event_type,
        subject_kind=subject_kind,
        subject_id=stable_subject_id,
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        channel_id=channel_id,
        occurred_at=_event_time_to_iso(payload.get("event_time") or (payload.get("event") or {}).get("event_ts")),
        source_refs={"workspace": workspace_name or None, "raw_event_id": raw_id, **(source_refs or {})},
        payload=event_payload or {},
    )


def _apply_event(conn, workspace_id: int, payload: dict[str, Any]) -> str:
    ev = payload.get("event") or {}
    ev_type = ev.get("type")

    if ev_type == "message":
        channel_id = ev.get("channel")
        if channel_id:
            subtype = ev.get("subtype")
            upsert_channel(conn, workspace_id, {"id": channel_id, "name": channel_id})

            if subtype == "message_changed":
                nested = ev.get("message") or {}
                if nested:
                    nested["channel"] = channel_id
                    upsert_message(conn, workspace_id, channel_id, nested)
                    ts = str(nested.get("ts") or "")
                    _record_child_event(
                        conn,
                        workspace_id,
                        payload,
                        event_type="slack.message.changed",
                        subject_kind="slack-message",
                        subject_id=f"message|{channel_id}|{ts}",
                        raw_suffix=f"message_changed|{channel_id}|{ts}",
                        actor_user_id=nested.get("user") or ev.get("user"),
                        channel_id=channel_id,
                        source_refs={"channel_id": channel_id, "ts": ts, "user_id": nested.get("user") or ev.get("user")},
                        event_payload={"textPreview": str(nested.get("text") or "")[:160]},
                    )
                    return "processed:message_changed"
                return "ignored:message_changed_missing_nested"

            if subtype == "message_deleted":
                deleted = {
                    "ts": ev.get("deleted_ts") or (ev.get("previous_message") or {}).get("ts"),
                    "subtype": "message_deleted",
                    "text": "",
                    "channel": channel_id,
                }
                if deleted.get("ts"):
                    upsert_message(conn, workspace_id, channel_id, deleted)
                    ts = str(deleted.get("ts") or "")
                    _record_child_event(
                        conn,
                        workspace_id,
                        payload,
                        event_type="slack.message.deleted",
                        subject_kind="slack-message",
                        subject_id=f"message|{channel_id}|{ts}",
                        raw_suffix=f"message_deleted|{channel_id}|{ts}",
                        actor_user_id=ev.get("user") or (ev.get("previous_message") or {}).get("user"),
                        channel_id=channel_id,
                        source_refs={"channel_id": channel_id, "ts": ts, "user_id": ev.get("user") or (ev.get("previous_message") or {}).get("user")},
                        event_payload={},
                    )
                    return "processed:message_deleted"
                return "ignored:message_deleted_missing_ts"

            upsert_message(conn, workspace_id, channel_id, ev)
            ts = str(ev.get("ts") or "")
            is_reply = bool(ev.get("thread_ts")) and str(ev.get("thread_ts")) != ts
            _record_child_event(
                conn,
                workspace_id,
                payload,
                event_type="slack.thread_reply.created" if is_reply else "slack.message.created",
                subject_kind="slack-message",
                subject_id=f"message|{channel_id}|{ts}",
                raw_suffix=f"message|{channel_id}|{ts}",
                actor_user_id=ev.get("user") or ev.get("bot_id"),
                channel_id=channel_id,
                source_refs={
                    "channel_id": channel_id,
                    "ts": ts,
                    "thread_ts": ev.get("thread_ts"),
                    "user_id": ev.get("user") or ev.get("bot_id"),
                },
                event_payload={"textPreview": str(ev.get("text") or "")[:160], "subtype": subtype},
            )
            return "processed:message"
        return "ignored:message_no_channel"

    if ev_type == "channel_created":
        channel = ev.get("channel") or {}
        if channel.get("id"):
            upsert_channel(conn, workspace_id, channel)
            return "processed:channel_created"
        return "ignored:channel_created_missing_id"

    if ev_type == "channel_rename":
        channel = {
            "id": ev.get("channel", {}).get("id"),
            "name": ev.get("channel", {}).get("name"),
        }
        if channel.get("id"):
            upsert_channel(conn, workspace_id, channel)
            return "processed:channel_rename"
        return "ignored:channel_rename_missing_id"

    if ev_type == "member_joined_channel":
        channel_id = ev.get("channel")
        user_id = ev.get("user")
        if channel_id and user_id:
            upsert_channel(conn, workspace_id, {"id": channel_id, "name": channel_id})
            upsert_channel_member(conn, workspace_id, channel_id, user_id)
            _record_child_event(
                conn,
                workspace_id,
                payload,
                event_type="slack.channel.member_joined",
                subject_kind="slack-channel",
                subject_id=str(channel_id),
                raw_suffix=f"member_joined_channel|{channel_id}|{user_id}",
                actor_user_id=str(user_id),
                channel_id=str(channel_id),
                source_refs={"channel_id": channel_id, "user_id": user_id},
                event_payload={},
            )
            return "processed:member_joined_channel"
        return "ignored:member_joined_channel_missing_fields"

    if ev_type == "member_left_channel":
        channel_id = ev.get("channel")
        user_id = ev.get("user")
        if channel_id and user_id:
            remove_channel_member(conn, workspace_id, channel_id, user_id)
            _record_child_event(
                conn,
                workspace_id,
                payload,
                event_type="slack.channel.member_left",
                subject_kind="slack-channel",
                subject_id=str(channel_id),
                raw_suffix=f"member_left_channel|{channel_id}|{user_id}",
                actor_user_id=str(user_id),
                channel_id=str(channel_id),
                source_refs={"channel_id": channel_id, "user_id": user_id},
                event_payload={},
            )
            return "processed:member_left_channel"
        return "ignored:member_left_channel_missing_fields"

    if ev_type in {"reaction_added", "reaction_removed"}:
        item = ev.get("item") or {}
        channel_id = item.get("channel")
        ts = item.get("ts")
        user_id = ev.get("user")
        reaction = ev.get("reaction")
        if channel_id and ts and user_id and reaction:
            event_type = "slack.reaction.added" if ev_type == "reaction_added" else "slack.reaction.removed"
            _record_child_event(
                conn,
                workspace_id,
                payload,
                event_type=event_type,
                subject_kind="slack-message",
                subject_id=f"message|{channel_id}|{ts}",
                raw_suffix=f"{ev_type}|{channel_id}|{ts}|{user_id}|{reaction}",
                actor_user_id=str(user_id),
                channel_id=str(channel_id),
                source_refs={"channel_id": channel_id, "ts": ts, "user_id": user_id, "reaction": reaction},
                event_payload={"reaction": reaction, "itemUser": ev.get("item_user")},
            )
            return f"processed:{ev_type}"
        return f"ignored:{ev_type}_missing_fields"

    if ev_type == "user_change":
        user = ev.get("user") or {}
        user_id = user.get("id")
        profile = user.get("profile") or {}
        if user_id:
            _record_child_event(
                conn,
                workspace_id,
                payload,
                event_type="slack.user.profile.changed",
                subject_kind="slack-user",
                subject_id=str(user_id),
                raw_suffix=f"user_change|{user_id}",
                actor_user_id=str(user_id),
                actor_label=profile.get("display_name") or user.get("real_name") or user.get("name"),
                source_refs={"user_id": user_id},
                event_payload={
                    "statusText": profile.get("status_text"),
                    "statusEmoji": profile.get("status_emoji"),
                    "displayName": profile.get("display_name"),
                },
            )
            return "processed:user_change"
        return "ignored:user_change_missing_user"

    if ev_type in {"file_created", "file_shared", "file_change"}:
        file_obj = ev.get("file") or {}
        if file_obj.get("id"):
            upsert_file(conn, workspace_id, file_obj)
            return f"processed:{ev_type}"
        return f"ignored:{ev_type}_missing_id"

    return f"ignored:{ev_type or 'unknown'}"


def process_pending_events(conn, workspace_id: int, limit: int = 100) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT event_id, payload_json
        FROM events
        WHERE workspace_id = ? AND status = 'pending'
        ORDER BY event_ts, event_id
        LIMIT ?
        """,
        (workspace_id, limit),
    ).fetchall()

    processed = 0
    errored = 0
    for row in rows:
        event_id = row["event_id"]
        try:
            payload = json.loads(row["payload_json"])
            detail = _apply_event(conn, workspace_id, payload)
            mark_event_status(conn, workspace_id, event_id, "processed", error=detail)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            mark_event_status(conn, workspace_id, event_id, "error", error=str(exc))
            errored += 1

    return {"processed": processed, "errored": errored, "scanned": len(rows)}


def run_processor_loop(
    conn, workspace_id: int, *, limit: int = 100, interval_seconds: float = 2.0, max_cycles: int | None = None
) -> dict[str, int]:
    total_processed = 0
    total_errored = 0
    cycles = 0
    while True:
        result = process_pending_events(conn, workspace_id, limit=limit)
        total_processed += result["processed"]
        total_errored += result["errored"]
        cycles += 1

        if max_cycles is not None and cycles >= max_cycles:
            break

        if result["scanned"] == 0:
            time.sleep(interval_seconds)
        else:
            time.sleep(0.1)

    return {"processed": total_processed, "errored": total_errored, "cycles": cycles}
