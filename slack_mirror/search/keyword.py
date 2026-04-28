from __future__ import annotations

import sqlite3
import shlex
from array import array
from datetime import date, datetime, time, timezone, timedelta
from typing import Any

from slack_mirror.search.embeddings import EmbeddingProvider, cosine_similarity, embed_text
from slack_mirror.search.query_syntax import ATTACHMENT_TYPE_MIME_PREFIXES, parse_derived_text_query
from slack_mirror.search.rerankers import RerankerProvider, rerank_rows
from slack_mirror.search.sqlite_adapter import SQLiteCorpusAdapter


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


def _glob_to_like(value: str) -> str:
    # simple glob-style wildcard support for source/channel filters
    return (value or "").replace("*", "%")


def _parse_temporal_value(value: str) -> tuple[float, str]:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("empty temporal filter value")
    try:
        return float(raw), "numeric"
    except ValueError:
        pass

    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        parsed_date = date.fromisoformat(raw)
        return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc).timestamp(), "date"

    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.timestamp(), "datetime"


def _append_lower_bound_clause(clauses: list[str], params: list[Any], value: str, *, negated: bool) -> None:
    ts, _ = _parse_temporal_value(value)
    clause = "CAST(m.ts AS REAL) >= ?"
    clauses.append(f"NOT ({clause})" if negated else clause)
    params.append(ts)


def _append_upper_bound_clause(clauses: list[str], params: list[Any], value: str, *, negated: bool) -> None:
    ts, kind = _parse_temporal_value(value)
    clause = "CAST(m.ts AS REAL) <= ?" if kind == "numeric" else "CAST(m.ts AS REAL) < ?"
    clauses.append(f"NOT ({clause})" if negated else clause)
    params.append(ts)


def _append_on_clause(clauses: list[str], params: list[Any], value: str, *, negated: bool) -> None:
    start_ts, _ = _parse_temporal_value(value)
    start = datetime.fromtimestamp(start_ts, tz=timezone.utc).date()
    lower = datetime.combine(start, time.min, tzinfo=timezone.utc).timestamp()
    upper = datetime.combine(start + timedelta(days=1), time.min, tzinfo=timezone.utc).timestamp()
    clause = "(CAST(m.ts AS REAL) >= ? AND CAST(m.ts AS REAL) < ?)"
    clauses.append(f"NOT {clause}" if negated else clause)
    params.extend([lower, upper])


def _append_file_metadata_clause(clauses: list[str], params: list[Any], raw_query: str) -> None:
    parsed = parse_derived_text_query(raw_query)
    if not parsed.has_structured_filters:
        return

    file_clauses: list[str] = []
    if parsed.has_attachment:
        file_clauses.append("1 = 1")

    for term in parsed.filename_terms:
        file_clauses.append(
            """LOWER(
              COALESCE(f.name, '') || ' ' ||
              COALESCE(f.title, '') || ' ' ||
              COALESCE(f.local_path, '') ||
              COALESCE(f.file_id, '')
            ) LIKE ?"""
        )
        params.append(f"%{term.lower()}%")

    for term in parsed.mime_terms:
        media_expr = "LOWER(COALESCE(f.mimetype, ''))"
        if term.endswith("/*"):
            file_clauses.append(f"{media_expr} LIKE ?")
            params.append(f"{term[:-1]}%")
        elif "*" in term:
            file_clauses.append(f"{media_expr} LIKE ?")
            params.append(term.replace("*", "%"))
        else:
            file_clauses.append(f"{media_expr} = ?")
            params.append(term)

    for ext in parsed.extensions:
        file_clauses.append(
            """(
              LOWER(COALESCE(f.name, '')) LIKE ?
              OR LOWER(COALESCE(f.title, '')) LIKE ?
              OR LOWER(COALESCE(f.local_path, '')) LIKE ?
            )"""
        )
        suffix = f"%.{ext.lower()}"
        params.extend([suffix, suffix, suffix])

    for attachment_type in parsed.attachment_types:
        prefixes = ATTACHMENT_TYPE_MIME_PREFIXES.get(attachment_type)
        if not prefixes:
            file_clauses.append("LOWER(COALESCE(f.mimetype, '')) LIKE ?")
            params.append(f"%{attachment_type.lower()}%")
            continue
        parts = []
        for prefix in prefixes:
            parts.append("LOWER(COALESCE(f.mimetype, '')) LIKE ?")
            params.append(f"{prefix.lower()}%")
        file_clauses.append("(" + " OR ".join(parts) + ")")

    clauses.append(
        """EXISTS (
            SELECT 1
            FROM message_files mf
            JOIN files f
              ON f.workspace_id = mf.workspace_id
             AND f.file_id = mf.file_id
            WHERE mf.workspace_id = m.workspace_id
              AND mf.channel_id = m.channel_id
              AND mf.ts = m.ts
              AND """
        + " AND ".join(file_clauses)
        + "\n        )"
    )


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

        if token.startswith("from:") or token.startswith("participant:") or token.startswith("user:"):
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

        if token.startswith("in:"):
            raw_values = [v.strip() for v in token.split(":", 1)[1].split(",") if v.strip()]
            if raw_values:
                parts: list[str] = []
                for raw in raw_values:
                    value = _normalize_channel_ref(raw)
                    if "*" in value:
                        parts.append(
                            """m.channel_id IN (
                                SELECT ch.channel_id
                                FROM channels ch
                                WHERE ch.workspace_id = m.workspace_id
                                  AND lower(COALESCE(ch.name, '')) LIKE lower(?)
                            )"""
                        )
                        params.append(_glob_to_like(value))
                    else:
                        parts.append(
                            """(
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
                        )
                        params.extend([value, value, value])
                clause = "(" + " OR ".join(parts) + ")"
                clauses.append(f"NOT {clause}" if negated else clause)
            continue

        if token.startswith("source:") or token.startswith("channel:"):
            value = _normalize_channel_ref(token.split(":", 1)[1])
            if "*" in value:
                clause = """m.channel_id IN (
                    SELECT ch.channel_id
                    FROM channels ch
                    WHERE ch.workspace_id = m.workspace_id
                      AND lower(COALESCE(ch.name, '')) LIKE lower(?)
                )"""
                clauses.append(f"NOT ({clause})" if negated else clause)
                params.append(_glob_to_like(value))
                continue

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

        if token.startswith("before:") or token.startswith("until:"):
            _append_upper_bound_clause(clauses, params, token.split(":", 1)[1], negated=negated)
            continue

        if token.startswith("after:") or token.startswith("since:"):
            _append_lower_bound_clause(clauses, params, token.split(":", 1)[1], negated=negated)
            continue

        if token.startswith("on:"):
            _append_on_clause(clauses, params, token.split(":", 1)[1], negated=negated)
            continue

        if token.startswith("has:"):
            value = token.split(":", 1)[1].lower()
            if value == "link":
                clause = "(COALESCE(m.text,'') LIKE '%http://%' OR COALESCE(m.text,'') LIKE '%https://%')"
                clauses.append(f"NOT {clause}" if negated else clause)
            elif value in {"attachment", "attachments", "file", "files"}:
                if negated:
                    clauses.append(
                        """NOT EXISTS (
                            SELECT 1
                            FROM message_files mf
                            WHERE mf.workspace_id = m.workspace_id
                              AND mf.channel_id = m.channel_id
                              AND mf.ts = m.ts
                        )"""
                    )
            continue

        if (
            token.startswith("filename:")
            or token.startswith("file:")
            or token.startswith("mime:")
            or token.startswith("extension:")
            or token.startswith("ext:")
            or token.startswith("attachment-type:")
        ):
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

    _append_file_metadata_clause(clauses, params, raw_query)
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


def _rank_rows(
    rows: list[dict[str, Any]],
    positive_terms: list[str],
    *,
    term_weight: float = 5.0,
    link_weight: float = 1.0,
    thread_weight: float = 0.5,
    recency_weight: float = 2.0,
) -> list[dict[str, Any]]:
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
        channel_text = f"{r.get('channel_id') or ''} {r.get('channel_name') or ''}".lower()
        term_hits = 0
        channel_term_hits = 0
        for t in positive_terms:
            tt = (t or "").lower().strip()
            if tt:
                term_hits += text.count(tt)
                channel_term_hits += channel_text.count(tt)

        has_link = ("http://" in text) or ("https://" in text)
        is_thread = bool(r.get("thread_ts"))

        try:
            ts = float(r.get("ts") or 0.0)
        except Exception:
            ts = 0.0
        recency = (ts / max_ts) if max_ts > 0 else 0.0

        score = (
            (term_hits * term_weight)
            + (channel_term_hits * term_weight)
            + (link_weight if has_link else 0.0)
            + (thread_weight if is_thread else 0.0)
            + (recency * recency_weight)
        )
        ranked.append({**r, "_score": round(score, 4)})

    ranked.sort(key=lambda x: (x.get("_score", 0.0), float(x.get("ts") or 0.0)), reverse=True)
    return ranked


def _has_channel_label_term(conn: sqlite3.Connection, *, workspace_id: int, terms: list[str]) -> bool:
    for term in terms:
        value = str(term or "").strip()
        if not value:
            continue
        row = conn.execute(
            """
            SELECT 1
            FROM channels
            WHERE workspace_id = ?
              AND (
                channel_id LIKE ?
                OR lower(COALESCE(name, '')) LIKE lower(?)
              )
            LIMIT 1
            """,
            (workspace_id, f"%{value}%", f"%{value}%"),
        ).fetchone()
        if row:
            return True
    return False


def _channel_label_candidates(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    terms: list[str],
    candidate_limit: int,
) -> list[dict[str, Any]]:
    term_values = [str(term or "").strip() for term in terms if str(term or "").strip()]
    if not term_values:
        return []

    matching_channels: dict[str, set[str]] = {}
    for term in term_values:
        rows = conn.execute(
            """
            SELECT channel_id
            FROM channels
            WHERE workspace_id = ?
              AND (
                channel_id LIKE ?
                OR lower(COALESCE(name, '')) LIKE lower(?)
              )
            LIMIT 50
            """,
            (workspace_id, f"%{term}%", f"%{term}%"),
        ).fetchall()
        if rows:
            matching_channels[term] = {str(row["channel_id"]) for row in rows}

    if not matching_channels:
        return []

    clauses = ["m.workspace_id = ?", "m.deleted = 0"]
    params: list[Any] = [workspace_id]
    for term in term_values:
        like = f"%{term}%"
        channels = sorted(matching_channels.get(term) or [])
        if channels:
            placeholders = ", ".join("?" for _ in channels)
            clauses.append(f"(COALESCE(m.text, '') LIKE ? OR m.channel_id IN ({placeholders}))")
            params.extend([like, *channels])
        else:
            clauses.append("COALESCE(m.text, '') LIKE ?")
            params.append(like)

    rows = conn.execute(
        f"""
        SELECT
          m.channel_id,
          c.name AS channel_name,
          m.ts,
          m.user_id,
          u.username AS user_name,
          u.display_name AS user_display_name,
          COALESCE(u.display_name, u.real_name, u.username) AS user_label,
          m.text,
          m.subtype,
          m.thread_ts,
          m.edited_ts,
          m.deleted
        FROM messages m
        LEFT JOIN channels c
          ON c.workspace_id = m.workspace_id AND c.channel_id = m.channel_id
        LEFT JOIN users u
          ON u.workspace_id = m.workspace_id AND u.user_id = m.user_id
        WHERE {" AND ".join(clauses)}
        ORDER BY CAST(m.ts AS REAL) DESC
        LIMIT ?
        """,
        (*params, max(1, int(candidate_limit))),
    ).fetchall()
    return [dict(row) for row in rows]


def _search_lexical(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    limit: int,
    use_fts: bool,
    rank_term_weight: float,
    rank_link_weight: float,
    rank_thread_weight: float,
    rank_recency_weight: float,
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

    candidate_limit = max(max(1, limit) * 5, 100)
    adapter = SQLiteCorpusAdapter(conn)
    needs_channel_label_fallback = bool(fts_sql) and _has_channel_label_term(conn, workspace_id=workspace_id, terms=positive_terms)
    rows = adapter.lexical_candidates(
        workspace_id=workspace_id,
        where_sql=where_sql,
        params=params,
        fts_sql=fts_sql,
        fts_params=fts_params,
        candidate_limit=candidate_limit,
        fallback_without_fts=needs_channel_label_fallback,
    )
    if needs_channel_label_fallback:
        seen = {(str(row.get("channel_id")), str(row.get("ts"))) for row in rows}
        for row in _channel_label_candidates(
            conn,
            workspace_id=workspace_id,
            terms=positive_terms,
            candidate_limit=max(max(1, limit) * 2, 20),
        ):
            key = (str(row.get("channel_id")), str(row.get("ts")))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    ranked = _rank_rows(
        rows,
        positive_terms,
        term_weight=rank_term_weight,
        link_weight=rank_link_weight,
        thread_weight=rank_thread_weight,
        recency_weight=rank_recency_weight,
    )[: max(1, limit)]
    for r in ranked:
        r.setdefault("_source", "lexical")
    return ranked


def _search_semantic(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    model_id: str,
    limit: int,
    provider: EmbeddingProvider | None = None,
) -> list[dict[str, Any]]:
    positive_terms, where_sql, params = _parse_query(query, include_term_clauses=False)
    query_vec = embed_text(" ".join(positive_terms) if positive_terms else query, model_id=model_id, provider=provider)
    candidate_limit = max(max(1, limit) * 8, 200)

    adapter = SQLiteCorpusAdapter(conn)
    rows = adapter.semantic_candidates(
        workspace_id=workspace_id,
        where_sql=where_sql,
        params=params,
        model_id=model_id,
        candidate_limit=candidate_limit,
    )

    scored: list[dict[str, Any]] = []
    for r in rows:
        vec = array("f")
        vec.frombytes(r["embedding_blob"])
        sem = cosine_similarity(query_vec, vec.tolist())
        scored.append({**r, "_semantic_score": round(sem, 6)})

    scored.sort(key=lambda x: (x.get("_semantic_score", 0.0), float(x.get("ts") or 0.0)), reverse=True)
    for s in scored:
        s.pop("embedding_blob", None)
        s.pop("dim", None)
        s.setdefault("_source", "semantic")
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
    lexical_weight: float = 0.6,
    semantic_weight: float = 0.4,
    semantic_scale: float = 10.0,
    rank_term_weight: float = 5.0,
    rank_link_weight: float = 1.0,
    rank_thread_weight: float = 0.5,
    rank_recency_weight: float = 2.0,
    rerank: bool = False,
    rerank_top_n: int = 50,
    provider: EmbeddingProvider | None = None,
    reranker_provider: RerankerProvider | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    mode = (mode or "lexical").lower()
    if mode == "lexical":
        out = _search_lexical(
            conn,
            workspace_id=workspace_id,
            query=q,
            limit=limit,
            use_fts=use_fts,
            rank_term_weight=rank_term_weight,
            rank_link_weight=rank_link_weight,
            rank_thread_weight=rank_thread_weight,
            rank_recency_weight=rank_recency_weight,
        )
        return rerank_rows(out, query=q, top_n=rerank_top_n, provider=reranker_provider)[: max(1, limit)] if rerank else out
    if mode == "semantic":
        out = _search_semantic(conn, workspace_id=workspace_id, query=q, model_id=model_id, limit=limit, provider=provider)
        return rerank_rows(out, query=q, top_n=rerank_top_n, provider=reranker_provider)[: max(1, limit)] if rerank else out

    lexical = _search_lexical(
        conn,
        workspace_id=workspace_id,
        query=q,
        limit=max(limit * 2, 20),
        use_fts=use_fts,
        rank_term_weight=rank_term_weight,
        rank_link_weight=rank_link_weight,
        rank_thread_weight=rank_thread_weight,
        rank_recency_weight=rank_recency_weight,
    )
    semantic = _search_semantic(
        conn,
        workspace_id=workspace_id,
        query=q,
        model_id=model_id,
        limit=max(limit * 2, 20),
        provider=provider,
    )

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in lexical:
        key = (str(row.get("channel_id")), str(row.get("ts")))
        merged[key] = {
            **row,
            "_lexical_score": float(row.get("_score") or 0.0),
            "_semantic_score": 0.0,
            "_source": "lexical",
        }
    for row in semantic:
        key = (str(row.get("channel_id")), str(row.get("ts")))
        if key in merged:
            merged[key]["_semantic_score"] = float(row.get("_semantic_score") or 0.0)
            merged[key]["_source"] = "hybrid"
        else:
            merged[key] = {
                **row,
                "_lexical_score": 0.0,
                "_semantic_score": float(row.get("_semantic_score") or 0.0),
                "_source": "semantic",
            }

    for row in merged.values():
        row["_hybrid_score"] = round(
            (lexical_weight * float(row.get("_lexical_score") or 0.0))
            + (semantic_weight * float(row.get("_semantic_score") or 0.0) * semantic_scale),
            6,
        )

    out = sorted(merged.values(), key=lambda x: (float(x.get("_hybrid_score") or 0.0), float(x.get("ts") or 0.0)), reverse=True)
    if rerank:
        out = rerank_rows(out, query=q, top_n=rerank_top_n, provider=reranker_provider)
    return out[: max(1, limit)]
