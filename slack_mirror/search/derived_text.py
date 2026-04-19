from __future__ import annotations

from array import array
import shlex
import sqlite3
from typing import Any

from slack_mirror.search.embeddings import EmbeddingProvider, cosine_similarity, embed_text


def _fts_escape(term: str) -> str:
    t = (term or "").replace('"', '""').strip()
    return f'"{t}"' if t else ""


def _base_doc_sql(*, include_chunk: bool = False, include_chunk_embedding: bool = False) -> str:
    chunk_sql = ""
    if include_chunk:
        embedding_sql = "\n          , dte.embedding_blob" if include_chunk_embedding else ""
        chunk_sql = """
          , dc.chunk_index
          , dc.start_offset
          , dc.end_offset
          , dc.text AS matched_text
        """ + embedding_sql
    return f"""
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
          {chunk_sql}
        FROM derived_text dt
        LEFT JOIN files f
          ON dt.source_kind = 'file'
         AND f.workspace_id = dt.workspace_id
         AND f.file_id = dt.source_id
        LEFT JOIN canvases c
          ON dt.source_kind = 'canvas'
         AND c.workspace_id = dt.workspace_id
         AND c.canvas_id = dt.source_id
    """


def _doc_clauses(
    *,
    workspace_id: int,
    derivation_kind: str | None,
    source_kind: str | None,
    negative_terms: list[str],
) -> tuple[list[str], list[Any]]:
    clauses = ["dt.workspace_id = ?"]
    params: list[Any] = [workspace_id]
    if derivation_kind:
        clauses.append("dt.derivation_kind = ?")
        params.append(derivation_kind)
    if source_kind:
        clauses.append("dt.source_kind = ?")
        params.append(source_kind)
    for term in negative_terms:
        clauses.append("COALESCE(dt.text, '') NOT LIKE ?")
        params.append(f"%{term}%")
    return clauses, params


def _fetch_chunk_candidates(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    positive_terms: list[str],
    derivation_kind: str | None,
    source_kind: str | None,
    negative_terms: list[str],
    limit: int,
) -> list[sqlite3.Row]:
    clauses, params = _doc_clauses(
        workspace_id=workspace_id,
        derivation_kind=derivation_kind,
        source_kind=source_kind,
        negative_terms=negative_terms,
    )
    sql = _base_doc_sql(include_chunk=True) + """
        JOIN derived_text_chunks dc
          ON dc.derived_text_id = dt.id
    """
    if positive_terms:
        match = " AND ".join(_fts_escape(token) for token in positive_terms if _fts_escape(token))
        sql += """
        JOIN derived_text_chunks_fts fts
          ON fts.derived_text_id = dc.derived_text_id
         AND fts.chunk_index = dc.chunk_index
        """
        clauses.append("derived_text_chunks_fts MATCH ?")
        params.append(match)
    else:
        clauses.append("COALESCE(dc.text, '') LIKE ?")
        params.append(f"%{query.strip()}%")

    sql += f"""
        WHERE {" AND ".join(clauses)}
        ORDER BY dt.updated_at DESC, dc.chunk_index ASC
        LIMIT ?
    """
    params.append(max(limit * 12, 200))
    return conn.execute(sql, params).fetchall()


def _fetch_doc_fallback_candidates(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    positive_terms: list[str],
    derivation_kind: str | None,
    source_kind: str | None,
    negative_terms: list[str],
    limit: int,
) -> list[sqlite3.Row]:
    clauses, params = _doc_clauses(
        workspace_id=workspace_id,
        derivation_kind=derivation_kind,
        source_kind=source_kind,
        negative_terms=negative_terms,
    )
    sql = _base_doc_sql()
    if positive_terms:
        match = " AND ".join(_fts_escape(token) for token in positive_terms if _fts_escape(token))
        sql += """
        WHERE """
        sql += " AND ".join(clauses)
        sql += """
          AND NOT EXISTS (SELECT 1 FROM derived_text_chunks dc WHERE dc.derived_text_id = dt.id)
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
          ORDER BY dt.updated_at DESC, dt.id DESC
          LIMIT ?
        """
        params.extend([match, max(limit * 4, 50)])
    else:
        clauses.append("NOT EXISTS (SELECT 1 FROM derived_text_chunks dc WHERE dc.derived_text_id = dt.id)")
        clauses.append("COALESCE(dt.text, '') LIKE ?")
        params.append(f"%{query.strip()}%")
        sql += f"""
        WHERE {" AND ".join(clauses)}
        ORDER BY dt.updated_at DESC, dt.id DESC
        LIMIT ?
        """
        params.append(max(limit * 4, 50))
    return conn.execute(sql, params).fetchall()


def _fetch_chunk_semantic_candidates(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    model_id: str,
    derivation_kind: str | None,
    source_kind: str | None,
    negative_terms: list[str],
    limit: int,
) -> list[sqlite3.Row]:
    clauses, params = _doc_clauses(
        workspace_id=workspace_id,
        derivation_kind=derivation_kind,
        source_kind=source_kind,
        negative_terms=negative_terms,
    )
    sql = _base_doc_sql(include_chunk=True, include_chunk_embedding=True) + """
        JOIN derived_text_chunks dc
          ON dc.derived_text_id = dt.id
        LEFT JOIN derived_text_chunk_embeddings dte
          ON dte.derived_text_chunk_id = dc.id
         AND dte.model_id = ?
        WHERE """ + " AND ".join(clauses) + """
        ORDER BY dt.updated_at DESC, dc.chunk_index ASC
        LIMIT ?
    """
    params = [model_id, *params]
    params.append(max(limit * 16, 400))
    return conn.execute(sql, params).fetchall()


def _fetch_doc_semantic_fallback_candidates(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    derivation_kind: str | None,
    source_kind: str | None,
    negative_terms: list[str],
    limit: int,
) -> list[sqlite3.Row]:
    clauses, params = _doc_clauses(
        workspace_id=workspace_id,
        derivation_kind=derivation_kind,
        source_kind=source_kind,
        negative_terms=negative_terms,
    )
    clauses.append("NOT EXISTS (SELECT 1 FROM derived_text_chunks dc WHERE dc.derived_text_id = dt.id)")
    sql = _base_doc_sql() + f"""
        WHERE {" AND ".join(clauses)}
        ORDER BY dt.updated_at DESC, dt.id DESC
        LIMIT ?
    """
    params.append(max(limit * 8, 200))
    return conn.execute(sql, params).fetchall()


def _aggregate_chunk_rows(rows: list[sqlite3.Row], *, positive_terms: list[str]) -> list[dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        matched_text = str(item.get("matched_text") or item.get("text") or "")
        score = 0.0
        if positive_terms:
            lowered = matched_text.lower()
            score = float(sum(lowered.count(term.lower().strip()) for term in positive_terms if term.strip()))
        elif matched_text:
            score = 1.0
        derived_id = int(item["id"])
        existing = out.get(derived_id)
        candidate = {
            **item,
            "_score": score,
            "_source": "lexical",
        }
        if existing is None or score > float(existing.get("_score") or 0.0):
            out[derived_id] = candidate
        elif score == float(existing.get("_score") or 0.0):
            if (
                int(item.get("chunk_index") or 0) < int(existing.get("chunk_index") or 0)
                or str(item.get("updated_at") or "") > str(existing.get("updated_at") or "")
            ):
                out[derived_id] = candidate
    results = list(out.values())
    results.sort(key=lambda x: (float(x.get("_score") or 0.0), str(x.get("updated_at") or "")), reverse=True)
    return results


def search_derived_text(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    limit: int = 20,
    derivation_kind: str | None = None,
    source_kind: str | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    tokens = shlex.split(q)
    positive_terms = [token for token in tokens if token and not token.startswith("-") and ":" not in token]
    negative_terms = [token[1:] for token in tokens if token.startswith("-") and len(token) > 1]

    chunk_rows = _fetch_chunk_candidates(
        conn,
        workspace_id=workspace_id,
        query=q,
        positive_terms=positive_terms,
        derivation_kind=derivation_kind,
        source_kind=source_kind,
        negative_terms=negative_terms,
        limit=limit,
    )
    results = _aggregate_chunk_rows(chunk_rows, positive_terms=positive_terms)
    seen_ids = {int(row["id"]) for row in results}

    fallback_rows = _fetch_doc_fallback_candidates(
        conn,
        workspace_id=workspace_id,
        query=q,
        positive_terms=positive_terms,
        derivation_kind=derivation_kind,
        source_kind=source_kind,
        negative_terms=negative_terms,
        limit=limit,
    )
    for row in fallback_rows:
        item = dict(row)
        if int(item["id"]) in seen_ids:
            continue
        text = str(item.get("text") or "")
        score = 0.0
        if positive_terms:
            lowered = text.lower()
            score = float(sum(lowered.count(term.lower().strip()) for term in positive_terms if term.strip()))
        elif text:
            score = 1.0
        item["matched_text"] = text
        item["_score"] = score
        item["_source"] = "lexical"
        results.append(item)

    results.sort(key=lambda x: (float(x.get("_score") or 0.0), str(x.get("updated_at") or "")), reverse=True)
    return results[: max(1, limit)]


def search_derived_text_semantic(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    limit: int = 20,
    derivation_kind: str | None = None,
    source_kind: str | None = None,
    model_id: str = "local-hash-128",
    provider: EmbeddingProvider | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    tokens = shlex.split(q)
    positive_terms = [token for token in tokens if token and not token.startswith("-") and ":" not in token]
    negative_terms = [token[1:] for token in tokens if token.startswith("-") and len(token) > 1]
    qvec = embed_text(" ".join(positive_terms) if positive_terms else q, model_id=model_id, provider=provider)

    chunk_rows = _fetch_chunk_semantic_candidates(
        conn,
        workspace_id=workspace_id,
        model_id=model_id,
        derivation_kind=derivation_kind,
        source_kind=source_kind,
        negative_terms=negative_terms,
        limit=limit,
    )
    scored: dict[int, dict[str, Any]] = {}
    for row in chunk_rows:
        item = dict(row)
        matched_text = str(item.get("matched_text") or "")
        if item.get("embedding_blob") is not None:
            vec = array("f")
            vec.frombytes(item["embedding_blob"])
            chunk_vec = vec.tolist()
        else:
            chunk_vec = embed_text(matched_text, model_id=model_id, provider=provider)
        sem = cosine_similarity(qvec, chunk_vec)
        item["_semantic_score"] = round(sem, 6)
        item["_source"] = "semantic"
        derived_id = int(item["id"])
        existing = scored.get(derived_id)
        if existing is None or float(item["_semantic_score"]) > float(existing.get("_semantic_score") or 0.0):
            scored[derived_id] = item

    fallback_rows = _fetch_doc_semantic_fallback_candidates(
        conn,
        workspace_id=workspace_id,
        derivation_kind=derivation_kind,
        source_kind=source_kind,
        negative_terms=negative_terms,
        limit=limit,
    )
    for row in fallback_rows:
        item = dict(row)
        derived_id = int(item["id"])
        if derived_id in scored:
            continue
        text = str(item.get("text") or "")
        item["matched_text"] = text
        item["_semantic_score"] = round(cosine_similarity(qvec, embed_text(text, model_id=model_id, provider=provider)), 6)
        item["_source"] = "semantic"
        scored[derived_id] = item

    results = list(scored.values())
    results.sort(key=lambda x: (float(x.get("_semantic_score") or 0.0), str(x.get("updated_at") or "")), reverse=True)
    return results[: max(1, limit)]
