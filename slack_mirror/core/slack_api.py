from __future__ import annotations

from time import sleep
from typing import Any, Callable

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackApiClient:
    def __init__(
        self,
        token: str,
        pause_seconds: float = 0.5,
        rate_limit_buffer_seconds: float = 1.0,
        max_rate_limit_retries: int = 50,
    ):
        self.client = WebClient(token=token)
        self.pause_seconds = pause_seconds
        self.rate_limit_buffer_seconds = rate_limit_buffer_seconds
        self.max_rate_limit_retries = max_rate_limit_retries

    def _retry_after_seconds(self, exc: SlackApiError) -> float | None:
        response = getattr(exc, "response", None)
        if response is None:
            return None
        if response.get("error") != "ratelimited":
            return None
        headers = getattr(response, "headers", None) or {}
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after is None:
            return None
        try:
            return float(retry_after)
        except (TypeError, ValueError):
            return None

    def _call_with_backoff(self, fn: Callable[..., Any], /, **kwargs: Any) -> Any:
        attempts = 0
        while True:
            try:
                return fn(**kwargs)
            except SlackApiError as exc:
                retry_after = self._retry_after_seconds(exc)
                if retry_after is None:
                    raise
                attempts += 1
                if attempts > self.max_rate_limit_retries:
                    raise
                sleep(retry_after + self.rate_limit_buffer_seconds)

    def auth_test(self) -> dict[str, Any]:
        return self._call_with_backoff(self.client.auth_test).data

    def list_users(self) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            resp = self._call_with_backoff(self.client.users_list, limit=200, cursor=cursor)
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
            resp = self._call_with_backoff(
                self.client.conversations_list,
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

    def conversation_history(
        self,
        channel_id: str,
        oldest: str = "0",
        latest: str | None = None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {
                "channel": channel_id,
                "limit": 200,
                "cursor": cursor,
                "oldest": oldest,
                "inclusive": True,
            }
            if latest:
                params["latest"] = latest
            resp = self._call_with_backoff(self.client.conversations_history, **params)
            messages.extend(resp.get("messages", []))
            cursor = (resp.get("response_metadata") or {}).get("next_cursor") or None
            if not cursor:
                break
            sleep(self.pause_seconds)
        return messages

    def conversation_replies(
        self,
        channel_id: str,
        thread_ts: str,
        oldest: str = "0",
        latest: str | None = None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {
                "channel": channel_id,
                "ts": thread_ts,
                "limit": 200,
                "cursor": cursor,
                "oldest": oldest,
                "inclusive": True,
            }
            if latest:
                params["latest"] = latest
            resp = self._call_with_backoff(self.client.conversations_replies, **params)
            messages.extend(resp.get("messages", []))
            cursor = (resp.get("response_metadata") or {}).get("next_cursor") or None
            if not cursor:
                break
            sleep(self.pause_seconds)
        return messages

    def list_files(self, types: str | None = None) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = self._call_with_backoff(self.client.files_list, count=200, page=page, types=types)
            current = resp.get("files", [])
            files.extend(current)
            pages = (resp.get("paging") or {}).get("pages", 1)
            if page >= pages:
                break
            page += 1
            sleep(self.pause_seconds)
        return files

    def open_direct_message(self, *, user_id: str) -> dict[str, Any]:
        return self._call_with_backoff(self.client.conversations_open, users=user_id).data

    def send_message(self, *, channel: str, text: str, **kwargs: Any) -> dict[str, Any]:
        return self._call_with_backoff(self.client.chat_postMessage, channel=channel, text=text, **kwargs).data

    def send_thread_reply(self, *, channel: str, thread_ts: str, text: str, **kwargs: Any) -> dict[str, Any]:
        return self._call_with_backoff(
            self.client.chat_postMessage,
            channel=channel,
            thread_ts=thread_ts,
            text=text,
            **kwargs,
        ).data


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
