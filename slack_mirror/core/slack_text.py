from __future__ import annotations

import re
import sqlite3
from typing import Any


USER_MENTION_RE = re.compile(r"<@([A-Z0-9]+)(?:\|([^>]+))?>")
EMOJI_ALIAS_RE = re.compile(r":([a-z0-9_+\-]+):")
UNRESOLVED_USER_MENTION_PLACEHOLDER = "@unresolved-slack-user"

COMMON_SLACK_EMOJI_ALIASES = {
    "+1": "👍",
    "100": "💯",
    "bangbang": "‼️",
    "checkered_flag": "🏁",
    "eyes": "👀",
    "fire": "🔥",
    "heart": "❤️",
    "heavy_check_mark": "✔️",
    "information_source": "ℹ️",
    "memo": "📝",
    "ok_hand": "👌",
    "raised_hands": "🙌",
    "rocket": "🚀",
    "rotating_light": "🚨",
    "sparkles": "✨",
    "thumbsup": "👍",
    "warning": "⚠️",
    "white_check_mark": "✅",
    "x": "❌",
}


def slack_user_mention_ids(value: Any) -> set[str]:
    text = str(value or "")
    return {match.group(1) for match in USER_MENTION_RE.finditer(text)}


def workspace_user_mention_labels(conn: sqlite3.Connection, *, workspace_id: int, user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    placeholders = ", ".join("?" for _ in sorted(user_ids))
    rows = conn.execute(
        f"""
        SELECT user_id,
               COALESCE(NULLIF(display_name, ''), NULLIF(real_name, ''), NULLIF(username, ''), user_id) AS label
        FROM users
        WHERE workspace_id = ? AND user_id IN ({placeholders})
        """,
        (workspace_id, *sorted(user_ids)),
    ).fetchall()
    return {str(row["user_id"]): str(row["label"]) for row in rows if row["label"]}


def render_slack_display_text(value: Any, labels: dict[str, str]) -> str:
    text = str(value or "")

    def replace_mention(match: re.Match[str]) -> str:
        user_id = match.group(1)
        embedded_label = str(match.group(2) or "").strip()
        label = str(labels.get(user_id) or embedded_label or "").strip()
        if label and label != user_id:
            return f"@{label}"
        return UNRESOLVED_USER_MENTION_PLACEHOLDER

    def replace_emoji(match: re.Match[str]) -> str:
        alias = match.group(1).lower()
        return COMMON_SLACK_EMOJI_ALIASES.get(alias, match.group(0))

    return EMOJI_ALIAS_RE.sub(replace_emoji, USER_MENTION_RE.sub(replace_mention, text))


def render_guest_safe_user_mentions(value: Any, labels: dict[str, str]) -> str:
    return render_slack_display_text(value, labels)
