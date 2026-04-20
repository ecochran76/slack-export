from __future__ import annotations

import sqlite3
from typing import Any


class SQLiteCorpusAdapter:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def lexical_candidates(
        self,
        *,
        workspace_id: int,
        where_sql: str,
        params: list[Any],
        fts_sql: str,
        fts_params: list[Any],
        candidate_limit: int,
        fallback_without_fts: bool,
    ) -> list[dict[str, Any]]:
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
        rows = self.conn.execute(sql.format(fts_clause=fts_sql), (workspace_id, *params, *fts_params, candidate_limit)).fetchall()
        if fallback_without_fts and not rows:
            rows = self.conn.execute(sql.format(fts_clause=""), (workspace_id, *params, candidate_limit)).fetchall()
        return [dict(r) for r in rows]

    def semantic_candidates(
        self,
        *,
        workspace_id: int,
        where_sql: str,
        params: list[Any],
        model_id: str,
        candidate_limit: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
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
              m.deleted,
              e.embedding_blob,
              e.dim
            FROM messages m
            JOIN message_embeddings e
              ON e.workspace_id = m.workspace_id AND e.channel_id = m.channel_id AND e.ts = m.ts
            LEFT JOIN channels c
              ON c.workspace_id = m.workspace_id AND c.channel_id = m.channel_id
            WHERE {where_sql}
              AND e.model_id = ?
            ORDER BY CAST(m.ts AS REAL) DESC
            LIMIT ?
            """,
            (workspace_id, *params, model_id, max(1, int(candidate_limit))),
        ).fetchall()
        return [dict(r) for r in rows]
