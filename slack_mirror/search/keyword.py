from __future__ import annotations

import shlex
import sqlite3
from typing import Any


def _build_where_clause(raw_query: str) -> tuple[str, list[Any]]:
    tokens = shlex.split(raw_query)
    clauses: list[str] = ["m.workspace_id = ?", "m.deleted = 0"]
    params: list[Any] = []

    for token in tokens:
        negated = token.startswith("-")
        if negated:
            token = token[1:]

        if not token:
            continue

        if token.startswith("from:"):
            value = token.split(":", 1)[1]
            clause = "m.user_id = ?"
            if negated:
                clause = f"NOT ({clause})"
            clauses.append(clause)
            params.append(value)
            continue

        if token.startswith("channel:"):
            value = token.split(":", 1)[1]
            clause = "(m.channel_id = ? OR c.name = ?)"
            if negated:
                clause = f"NOT {clause}"
            clauses.append(clause)
            params.extend([value, value])
            continue

        if token.startswith("before:"):
            value = token.split(":", 1)[1]
            clause = "CAST(m.ts AS REAL) <= CAST(? AS REAL)"
            if negated:
                clause = f"NOT ({clause})"
            clauses.append(clause)
            params.append(value)
            continue

        if token.startswith("after:"):
            value = token.split(":", 1)[1]
            clause = "CAST(m.ts AS REAL) >= CAST(? AS REAL)"
            if negated:
                clause = f"NOT ({clause})"
            clauses.append(clause)
            params.append(value)
            continue

        if token.startswith("has:"):
            value = token.split(":", 1)[1].lower()
            if value == "link":
                clause = "(COALESCE(m.text,'') LIKE '%http://%' OR COALESCE(m.text,'') LIKE '%https://%')"
                if negated:
                    clause = f"NOT {clause}"
                clauses.append(clause)
            continue

        if token.startswith("is:"):
            value = token.split(":", 1)[1].lower()
            mapping = {
                "thread": "m.thread_ts IS NOT NULL",
                "reply": "(m.thread_ts IS NOT NULL AND m.thread_ts != m.ts)",
                "edited": "m.edited_ts IS NOT NULL",
            }
            clause = mapping.get(value)
            if clause:
                if negated:
                    clause = f"NOT ({clause})"
                clauses.append(clause)
            continue

        # Plain terms -> substring match on message text
        clause = "COALESCE(m.text, '') LIKE ?"
        if negated:
            clause = f"NOT ({clause})"
        clauses.append(clause)
        params.append(f"%{token}%")

    return " AND ".join(clauses), params


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

    where_sql, params = _build_where_clause(q)
    rows = conn.execute(
        f"""
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
        WHERE {where_sql}
        ORDER BY CAST(m.ts AS REAL) DESC
        LIMIT ?
        """,
        (workspace_id, *params, max(1, limit)),
    ).fetchall()
    return [dict(r) for r in rows]
