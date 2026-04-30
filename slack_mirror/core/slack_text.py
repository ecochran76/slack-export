from __future__ import annotations

import re
import sqlite3
from typing import Any


USER_MENTION_RE = re.compile(r"<@([A-Z0-9]+)(?:\|([^>]+))?>")
UNRESOLVED_USER_MENTION_PLACEHOLDER = "@unresolved-slack-user"


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


def render_guest_safe_user_mentions(value: Any, labels: dict[str, str]) -> str:
    text = str(value or "")

    def replace(match: re.Match[str]) -> str:
        user_id = match.group(1)
        embedded_label = str(match.group(2) or "").strip()
        label = str(labels.get(user_id) or embedded_label or "").strip()
        if label and label != user_id:
            return f"@{label}"
        return UNRESOLVED_USER_MENTION_PLACEHOLDER

    return USER_MENTION_RE.sub(replace, text)
