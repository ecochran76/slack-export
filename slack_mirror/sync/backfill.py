from __future__ import annotations

from slack_sdk.errors import SlackApiError

from slack_mirror.core.db import (
    get_sync_state,
    list_channel_ids,
    set_sync_state,
    upsert_channel,
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
