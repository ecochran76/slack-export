from __future__ import annotations

from time import sleep
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackApiClient:
    def __init__(self, token: str, pause_seconds: float = 0.5):
        self.client = WebClient(token=token)
        self.pause_seconds = pause_seconds

    def auth_test(self) -> dict[str, Any]:
        return self.client.auth_test().data

    def list_users(self) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            resp = self.client.users_list(limit=200, cursor=cursor)
            users.extend(resp.get("members", []))
            cursor = (resp.get("response_metadata") or {}).get("next_cursor") or None
            if not cursor:
                break
            sleep(self.pause_seconds)
        return users

    def list_conversations(self) -> list[dict[str, Any]]:
        conversations: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            resp = self.client.conversations_list(
                types="public_channel,private_channel,im,mpim",
                limit=1000,
                cursor=cursor,
                exclude_archived=False,
            )
            conversations.extend(resp.get("channels", []))
            cursor = (resp.get("response_metadata") or {}).get("next_cursor") or None
            if not cursor:
                break
            sleep(self.pause_seconds)
        return conversations

    def conversation_history(self, channel_id: str, oldest: str = "0") -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            resp = self.client.conversations_history(
                channel=channel_id,
                limit=200,
                cursor=cursor,
                oldest=oldest,
                inclusive=True,
            )
            messages.extend(resp.get("messages", []))
            cursor = (resp.get("response_metadata") or {}).get("next_cursor") or None
            if not cursor:
                break
            sleep(self.pause_seconds)
        return messages


def safe_auth_test(token: str) -> tuple[bool, str]:
    try:
        client = SlackApiClient(token)
        result = client.auth_test()
        team = result.get("team") or result.get("team_id") or "unknown-team"
        user = result.get("user") or result.get("user_id") or "unknown-user"
        return True, f"ok team={team} user={user}"
    except SlackApiError as exc:
        return False, f"slack_error={exc.response.get('error', 'unknown')}"
    except Exception as exc:  # noqa: BLE001
        return False, f"error={exc}"
