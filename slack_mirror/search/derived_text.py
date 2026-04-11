from __future__ import annotations

import shlex
import sqlite3
from typing import Any


def _fts_escape(term: str) -> str:
    t = (term or "").replace('"', '""').strip()
    return f'"{t}"' if t else ""


def search_derived_text(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    limit: int = 20,
    derivation_kind: str | None = None,
    source_kind: str | None = None,
) -> list[dict[str, Any]]:
    tokens = shlex.split(query or "")
    positive_terms = [token for token in tokens if token and not token.startswith("-") and ":" not in token]
    clauses = ["dt.workspace_id = ?"]
    params: list[Any] = [workspace_id]

    if derivation_kind:
        clauses.append("dt.derivation_kind = ?")
        params.append(derivation_kind)
    if source_kind:
        clauses.append("dt.source_kind = ?")
        params.append(source_kind)

    for token in tokens:
        if token.startswith("-") and len(token) > 1:
            clauses.append("COALESCE(dt.text, '') NOT LIKE ?")
            params.append(f"%{token[1:]}%")

    fts_sql = ""
    fts_params: list[Any] = []
    if positive_terms:
        match = " AND ".join(_fts_escape(token) for token in positive_terms if _fts_escape(token))
        if match:
            fts_sql = """
              AND EXISTS (
                SELECT 1
                FROM derived_text_fts fts
                WHERE fts.workspace_id = dt.workspace_id
                  AND fts.source_kind = dt.source_kind
                  AND fts.source_id = dt.source_id
                  AND fts.derivation_kind = dt.derivation_kind
                  AND fts.extractor = dt.extractor
                  AND derived_text_fts MATCH ?
              )
            """
            fts_params.append(match)
        else:
            clauses.append("COALESCE(dt.text, '') LIKE ?")
            params.append(f"%{query}%")
    elif query.strip():
        clauses.append("COALESCE(dt.text, '') LIKE ?")
        params.append(f"%{query.strip()}%")

    sql = f"""
        SELECT
          dt.id,
          dt.source_kind,
          dt.source_id,
          dt.derivation_kind,
          dt.extractor,
          dt.text,
          dt.media_type,
          dt.local_path,
          dt.updated_at,
          COALESCE(f.title, f.name, c.title, dt.source_id) AS source_label
        FROM derived_text dt
        LEFT JOIN files f
          ON dt.source_kind = 'file'
         AND f.workspace_id = dt.workspace_id
         AND f.file_id = dt.source_id
        LEFT JOIN canvases c
          ON dt.source_kind = 'canvas'
         AND c.workspace_id = dt.workspace_id
         AND c.canvas_id = dt.source_id
        WHERE {" AND ".join(clauses)}
        {fts_sql}
        ORDER BY dt.updated_at DESC, dt.id DESC
        LIMIT ?
    """
    rows = conn.execute(sql, (*params, *fts_params, limit)).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        text = str(item.get("text") or "").lower()
        term_hits = 0
        for term in positive_terms:
            tt = (term or "").lower().strip()
            if tt:
                term_hits += text.count(tt)
        item["_score"] = float(term_hits or (1 if positive_terms else 0))
        item["_source"] = "lexical"
        out.append(item)
    return out
