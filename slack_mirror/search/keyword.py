from __future__ import annotations

import sqlite3
from typing import Any


def search_messages(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    # Use LIKE against canonical messages table to avoid relying on FTS shadow-table wiring.
    like_q = f"%{q}%"
    rows = conn.execute(
        """
        SELECT
          m.channel_id,
          c.name AS channel_name,
          m.ts,
          m.user_id,
          m.text,
          m.subtype,
          m.thread_ts,
          m.edited_ts,
          m.deleted
        FROM messages m
        LEFT JOIN channels c
          ON c.workspace_id = m.workspace_id AND c.channel_id = m.channel_id
        WHERE m.workspace_id = ?
          AND m.deleted = 0
          AND COALESCE(m.text, '') LIKE ?
        ORDER BY CAST(m.ts AS REAL) DESC
        LIMIT ?
        """,
        (workspace_id, like_q, max(1, limit)),
    ).fetchall()
    return [dict(r) for r in rows]
