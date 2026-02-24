from __future__ import annotations

from slack_mirror.core.db import upsert_channel, upsert_user
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
