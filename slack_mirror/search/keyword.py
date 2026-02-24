from __future__ import annotations

import shlex
import sqlite3
from typing import Any


def _normalize_user_ref(value: str) -> str:
    v = (value or "").strip()
    if v.startswith("<@") and v.endswith(">"):
        return v[2:-1].split("|", 1)[0]
    if v.startswith("@"):
        return v[1:]
    return v


def _normalize_channel_ref(value: str) -> str:
    v = (value or "").strip()
    if v.startswith("<#") and v.endswith(">"):
        return v[2:-1].split("|", 1)[0]
    if v.startswith("#"):
        return v[1:]
    return v


def _fts_escape(term: str) -> str:
    t = (term or "").replace('"', '""').strip()
    return f'"{t}"' if t else ""


def _parse_query(raw_query: str) -> tuple[list[str], str, list[Any]]:
    tokens = shlex.split(raw_query)
    clauses: list[str] = ["m.workspace_id = ?", "m.deleted = 0"]
    params: list[Any] = []
    positive_terms: list[str] = []

    for token in tokens:
        negated = token.startswith("-")
        if negated:
            token = token[1:]
        if not token:
            continue

        if token.startswith("from:"):
            value = _normalize_user_ref(token.split(":", 1)[1])
            clause = """(
                m.user_id = ?
                OR m.user_id IN (
                    SELECT u.user_id
                    FROM users u
                    WHERE u.workspace_id = m.workspace_id
                      AND (
                        u.user_id = ?
                        OR lower(COALESCE(u.username, '')) = lower(?)
                        OR lower(COALESCE(u.display_name, '')) = lower(?)
                        OR lower(COALESCE(u.real_name, '')) = lower(?)
                      )
                )
            )"""
            clauses.append(f"NOT {clause}" if negated else clause)
            params.extend([value, value, value, value, value])
            continue

        if token.startswith("channel:"):
            value = _normalize_channel_ref(token.split(":", 1)[1])
            clause = """(
                m.channel_id = ?
                OR m.channel_id IN (
                    SELECT ch.channel_id
                    FROM channels ch
                    WHERE ch.workspace_id = m.workspace_id
                      AND (
                        ch.channel_id = ?
                        OR lower(COALESCE(ch.name, '')) = lower(?)
                      )
                )
            )"""
            clauses.append(f"NOT {clause}" if negated else clause)
            params.extend([value, value, value])
            continue

        if token.startswith("before:"):
            value = token.split(":", 1)[1]
            clause = "CAST(m.ts AS REAL) <= CAST(? AS REAL)"
            clauses.append(f"NOT ({clause})" if negated else clause)
            params.append(value)
            continue

        if token.startswith("after:"):
            value = token.split(":", 1)[1]
            clause = "CAST(m.ts AS REAL) >= CAST(? AS REAL)"
            clauses.append(f"NOT ({clause})" if negated else clause)
            params.append(value)
            continue

        if token.startswith("has:"):
            value = token.split(":", 1)[1].lower()
            if value == "link":
                clause = "(COALESCE(m.text,'') LIKE '%http://%' OR COALESCE(m.text,'') LIKE '%https://%')"
                clauses.append(f"NOT {clause}" if negated else clause)
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
                clauses.append(f"NOT ({clause})" if negated else clause)
            continue

        # Plain term
        if not negated:
            positive_terms.append(token)
        clause = "COALESCE(m.text, '') LIKE ?"
        clauses.append(f"NOT ({clause})" if negated else clause)
        params.append(f"%{token}%")

    where_sql = " AND ".join(clauses)
    return positive_terms, where_sql, params


def reindex_messages_fts(conn: sqlite3.Connection, *, workspace_id: int) -> int:
    with conn:
        conn.execute("DELETE FROM messages_fts WHERE workspace_id = ?", (workspace_id,))
        conn.execute(
            """
            INSERT INTO messages_fts(workspace_id, channel_id, user_id, ts, text)
            SELECT
              m.workspace_id,
              m.channel_id,
              COALESCE(m.user_id, ''),
              m.ts,
              COALESCE(m.text, '')
            FROM messages m
            WHERE m.workspace_id = ? AND m.deleted = 0
            """,
            (workspace_id,),
        )
    row = conn.execute("SELECT COUNT(*) AS c FROM messages_fts WHERE workspace_id = ?", (workspace_id,)).fetchone()
    return int(row[0] if row else 0)


def search_messages(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    limit: int = 20,
    use_fts: bool = True,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    positive_terms, where_sql, params = _parse_query(q)

    fts_sql = ""
    fts_params: list[Any] = []
    if use_fts and positive_terms:
        match = " AND ".join(_fts_escape(t) for t in positive_terms if _fts_escape(t))
        if match:
            fts_sql = """
              AND EXISTS (
                SELECT 1
                FROM messages_fts f
                WHERE f.workspace_id = m.workspace_id
                  AND f.channel_id = m.channel_id
                  AND f.ts = m.ts
                  AND f.user_id = COALESCE(m.user_id, '')
                  AND f.text MATCH ?
              )
            """
            fts_params.append(match)

    sql = f"""
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
          {{fts_clause}}
        ORDER BY CAST(m.ts AS REAL) DESC
        LIMIT ?
    """

    # First pass (optional FTS prefilter)
    rows = conn.execute(
        sql.format(fts_clause=fts_sql),
        (workspace_id, *params, *fts_params, max(1, limit)),
    ).fetchall()

    # Fallback if FTS index is stale/missing for this workspace.
    if use_fts and positive_terms and not rows:
        rows = conn.execute(
            sql.format(fts_clause=""),
            (workspace_id, *params, max(1, limit)),
        ).fetchall()

    return [dict(r) for r in rows]
