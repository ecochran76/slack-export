from __future__ import annotations

import json
import time
from typing import Any

from slack_mirror.core.db import mark_event_status, upsert_channel, upsert_file, upsert_message


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
                    return "processed:message_deleted"
                return "ignored:message_deleted_missing_ts"

            upsert_message(conn, workspace_id, channel_id, ev)
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
