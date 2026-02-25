from __future__ import annotations

import math
import shlex
import sqlite3
from array import array
from hashlib import blake2b
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


def _parse_query(raw_query: str, *, include_term_clauses: bool = True) -> tuple[list[str], str, list[Any]]:
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
        if include_term_clauses or negated:
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


def _rank_rows(rows: list[dict[str, Any]], positive_terms: list[str]) -> list[dict[str, Any]]:
    if not rows:
        return rows

    max_ts = 0.0
    for r in rows:
        try:
            max_ts = max(max_ts, float(r.get("ts") or 0.0))
        except Exception:
            pass

    ranked: list[dict[str, Any]] = []
    for r in rows:
        text = (r.get("text") or "").lower()
        term_hits = 0
        for t in positive_terms:
            tt = (t or "").lower().strip()
            if tt:
                term_hits += text.count(tt)

        has_link = ("http://" in text) or ("https://" in text)
        is_thread = bool(r.get("thread_ts"))

        try:
            ts = float(r.get("ts") or 0.0)
        except Exception:
            ts = 0.0
        recency = (ts / max_ts) if max_ts > 0 else 0.0

        score = (term_hits * 5.0) + (1.0 if has_link else 0.0) + (0.5 if is_thread else 0.0) + (recency * 2.0)
        ranked.append({**r, "_score": round(score, 4)})

    ranked.sort(key=lambda x: (x.get("_score", 0.0), float(x.get("ts") or 0.0)), reverse=True)
    return ranked


def _embed_text_local(text: str, dim: int = 128) -> list[float]:
    vec = [0.0] * dim
    for tok in shlex.split((text or "").lower().replace("\n", " ")):
        h = blake2b(tok.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h, "little") % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def _search_lexical(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    limit: int,
    use_fts: bool,
) -> list[dict[str, Any]]:
    positive_terms, where_sql, params = _parse_query(query)

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
    candidate_limit = max(max(1, limit) * 5, 100)
    rows = conn.execute(sql.format(fts_clause=fts_sql), (workspace_id, *params, *fts_params, candidate_limit)).fetchall()
    if use_fts and positive_terms and not rows:
        rows = conn.execute(sql.format(fts_clause=""), (workspace_id, *params, candidate_limit)).fetchall()
    return _rank_rows([dict(r) for r in rows], positive_terms)[: max(1, limit)]


def _search_semantic(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    model_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    positive_terms, where_sql, params = _parse_query(query, include_term_clauses=False)
    query_vec = _embed_text_local(" ".join(positive_terms) if positive_terms else query)
    candidate_limit = max(max(1, limit) * 8, 200)

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
        (workspace_id, *params, model_id, candidate_limit),
    ).fetchall()

    scored: list[dict[str, Any]] = []
    for r in rows:
        vec = array("f")
        vec.frombytes(r["embedding_blob"])
        sem = _cosine(query_vec, vec.tolist())
        scored.append({**dict(r), "_semantic_score": round(sem, 6)})

    scored.sort(key=lambda x: (x.get("_semantic_score", 0.0), float(x.get("ts") or 0.0)), reverse=True)
    for s in scored:
        s.pop("embedding_blob", None)
        s.pop("dim", None)
    return scored[: max(1, limit)]


def search_messages(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    limit: int = 20,
    use_fts: bool = True,
    mode: str = "lexical",
    model_id: str = "local-hash-128",
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    mode = (mode or "lexical").lower()
    if mode == "lexical":
        return _search_lexical(conn, workspace_id=workspace_id, query=q, limit=limit, use_fts=use_fts)
    if mode == "semantic":
        return _search_semantic(conn, workspace_id=workspace_id, query=q, model_id=model_id, limit=limit)

    lexical = _search_lexical(conn, workspace_id=workspace_id, query=q, limit=max(limit * 2, 20), use_fts=use_fts)
    semantic = _search_semantic(conn, workspace_id=workspace_id, query=q, model_id=model_id, limit=max(limit * 2, 20))

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in lexical:
        key = (str(row.get("channel_id")), str(row.get("ts")))
        merged[key] = {**row, "_lexical_score": float(row.get("_score") or 0.0), "_semantic_score": 0.0}
    for row in semantic:
        key = (str(row.get("channel_id")), str(row.get("ts")))
        if key in merged:
            merged[key]["_semantic_score"] = float(row.get("_semantic_score") or 0.0)
        else:
            merged[key] = {**row, "_lexical_score": 0.0, "_semantic_score": float(row.get("_semantic_score") or 0.0)}

    for row in merged.values():
        row["_hybrid_score"] = round((0.6 * float(row.get("_lexical_score") or 0.0)) + (0.4 * float(row.get("_semantic_score") or 0.0) * 10.0), 6)

    out = sorted(merged.values(), key=lambda x: (float(x.get("_hybrid_score") or 0.0), float(x.get("ts") or 0.0)), reverse=True)
    return out[: max(1, limit)]
