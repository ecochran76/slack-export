from __future__ import annotations

import math
import shlex
import sqlite3
from array import array
from hashlib import blake2b
from typing import Any

from slack_mirror.search.derived_text import search_derived_text
from slack_mirror.search.keyword import search_messages


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


def _search_derived_text_semantic(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    limit: int,
    derivation_kind: str | None = None,
    source_kind: str | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    tokens = shlex.split(q)
    positive_terms = [token for token in tokens if token and not token.startswith("-") and ":" not in token]
    qvec = _embed_text_local(" ".join(positive_terms) if positive_terms else q)

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
        ORDER BY dt.updated_at DESC, dt.id DESC
        LIMIT ?
    """
    rows = conn.execute(sql, (*params, max(limit * 8, 200))).fetchall()
    scored: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        sem = _cosine(qvec, _embed_text_local(str(item.get("text") or "")))
        item["_semantic_score"] = round(sem, 6)
        item["_source"] = "semantic"
        scored.append(item)
    scored.sort(key=lambda x: (float(x.get("_semantic_score") or 0.0), str(x.get("updated_at") or "")), reverse=True)
    return scored[: max(1, limit)]


def _message_key(row: dict[str, Any]) -> tuple[str, str]:
    return ("message", f"{row.get('channel_id')}:{row.get('ts')}")


def _derived_key(row: dict[str, Any]) -> tuple[str, str]:
    return ("derived_text", f"{row.get('source_kind')}:{row.get('source_id')}:{row.get('derivation_kind')}:{row.get('extractor')}")


def _normalize_message_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "result_kind": "message",
        "sort_ts": str(row.get("ts") or ""),
        "source_label": row.get("channel_name") or row.get("channel_id"),
    }


def _normalize_derived_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "result_kind": "derived_text",
        "sort_ts": str(row.get("updated_at") or ""),
    }


def search_corpus(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    query: str,
    limit: int = 20,
    mode: str = "hybrid",
    model_id: str = "local-hash-128",
    lexical_weight: float = 0.6,
    semantic_weight: float = 0.4,
    semantic_scale: float = 10.0,
    use_fts: bool = True,
    derived_kind: str | None = None,
    derived_source_kind: str | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    mode = (mode or "hybrid").lower()
    lexical_limit = max(limit * 2, 20)

    if mode == "lexical":
        msg_rows = [_normalize_message_row(r) for r in search_messages(conn, workspace_id=workspace_id, query=q, limit=lexical_limit, use_fts=use_fts, mode="lexical")]
        derived_rows = [_normalize_derived_row(r) for r in search_derived_text(conn, workspace_id=workspace_id, query=q, limit=lexical_limit, derivation_kind=derived_kind, source_kind=derived_source_kind)]
        merged = msg_rows + derived_rows
        merged.sort(key=lambda x: (float(x.get("_score") or 0.0), x.get("sort_ts") or ""), reverse=True)
        return merged[: max(1, limit)]

    if mode == "semantic":
        msg_rows = [_normalize_message_row(r) for r in search_messages(conn, workspace_id=workspace_id, query=q, limit=lexical_limit, mode="semantic", model_id=model_id)]
        derived_rows = [_normalize_derived_row(r) for r in _search_derived_text_semantic(conn, workspace_id=workspace_id, query=q, limit=lexical_limit, derivation_kind=derived_kind, source_kind=derived_source_kind)]
        merged = msg_rows + derived_rows
        merged.sort(key=lambda x: (float(x.get("_semantic_score") or 0.0), x.get("sort_ts") or ""), reverse=True)
        return merged[: max(1, limit)]

    msg_lexical = [_normalize_message_row(r) for r in search_messages(conn, workspace_id=workspace_id, query=q, limit=lexical_limit, use_fts=use_fts, mode="lexical")]
    msg_semantic = [_normalize_message_row(r) for r in search_messages(conn, workspace_id=workspace_id, query=q, limit=lexical_limit, mode="semantic", model_id=model_id)]
    derived_lexical = [_normalize_derived_row(r) for r in search_derived_text(conn, workspace_id=workspace_id, query=q, limit=lexical_limit, derivation_kind=derived_kind, source_kind=derived_source_kind)]
    derived_semantic = [_normalize_derived_row(r) for r in _search_derived_text_semantic(conn, workspace_id=workspace_id, query=q, limit=lexical_limit, derivation_kind=derived_kind, source_kind=derived_source_kind)]

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in msg_lexical:
        merged[_message_key(row)] = {**row, "_lexical_score": float(row.get("_score") or 0.0), "_semantic_score": 0.0, "_source": "lexical"}
    for row in derived_lexical:
        merged[_derived_key(row)] = {**row, "_lexical_score": float(row.get("_score") or 0.0), "_semantic_score": 0.0, "_source": "lexical"}

    for row in msg_semantic:
        key = _message_key(row)
        if key in merged:
            merged[key]["_semantic_score"] = float(row.get("_semantic_score") or 0.0)
            merged[key]["_source"] = "hybrid"
        else:
            merged[key] = {**row, "_lexical_score": 0.0, "_semantic_score": float(row.get("_semantic_score") or 0.0), "_source": "semantic"}

    for row in derived_semantic:
        key = _derived_key(row)
        if key in merged:
            merged[key]["_semantic_score"] = float(row.get("_semantic_score") or 0.0)
            merged[key]["_source"] = "hybrid"
        else:
            merged[key] = {**row, "_lexical_score": 0.0, "_semantic_score": float(row.get("_semantic_score") or 0.0), "_source": "semantic"}

    for row in merged.values():
        row["_hybrid_score"] = round(
            (lexical_weight * float(row.get("_lexical_score") or 0.0))
            + (semantic_weight * float(row.get("_semantic_score") or 0.0) * semantic_scale),
            6,
        )

    out = sorted(
        merged.values(),
        key=lambda x: (float(x.get("_hybrid_score") or 0.0), x.get("sort_ts") or ""),
        reverse=True,
    )
    return out[: max(1, limit)]
