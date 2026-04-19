from __future__ import annotations

import sqlite3
from typing import Any

from slack_mirror.search.embeddings import EmbeddingProvider
from slack_mirror.search.derived_text import search_derived_text, search_derived_text_semantic
from slack_mirror.search.keyword import search_messages


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
        "snippet_text": row.get("matched_text") or row.get("text") or "",
    }


def _search_corpus_rows(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    workspace_name: str | None = None,
    query: str,
    limit: int = 20,
    offset: int = 0,
    mode: str = "hybrid",
    model_id: str = "local-hash-128",
    lexical_weight: float = 0.6,
    semantic_weight: float = 0.4,
    semantic_scale: float = 10.0,
    use_fts: bool = True,
    derived_kind: str | None = None,
    derived_source_kind: str | None = None,
    message_embedding_provider: EmbeddingProvider | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    mode = (mode or "hybrid").lower()
    requested_limit = max(1, int(limit or 20))
    requested_offset = max(0, int(offset or 0))
    lexical_limit = max((requested_limit + requested_offset) * 2, 20)

    if mode == "lexical":
        msg_rows = [_normalize_message_row(r) for r in search_messages(conn, workspace_id=workspace_id, query=q, limit=lexical_limit, use_fts=use_fts, mode="lexical")]
        derived_rows = [_normalize_derived_row(r) for r in search_derived_text(conn, workspace_id=workspace_id, query=q, limit=lexical_limit, derivation_kind=derived_kind, source_kind=derived_source_kind)]
        merged = msg_rows + derived_rows
        merged.sort(key=lambda x: (float(x.get("_score") or 0.0), x.get("sort_ts") or ""), reverse=True)
        for row in merged:
            row["workspace_id"] = workspace_id
            row["workspace"] = workspace_name
        return merged

    if mode == "semantic":
        msg_rows = [
            _normalize_message_row(r)
            for r in search_messages(
                conn,
                workspace_id=workspace_id,
                query=q,
                limit=lexical_limit,
                mode="semantic",
                model_id=model_id,
                provider=message_embedding_provider,
            )
        ]
        derived_rows = [
            _normalize_derived_row(r)
            for r in search_derived_text_semantic(
                conn,
                workspace_id=workspace_id,
                query=q,
                limit=lexical_limit,
                derivation_kind=derived_kind,
                source_kind=derived_source_kind,
                model_id=model_id,
                provider=message_embedding_provider,
            )
        ]
        merged = msg_rows + derived_rows
        merged.sort(key=lambda x: (float(x.get("_semantic_score") or 0.0), x.get("sort_ts") or ""), reverse=True)
        for row in merged:
            row["workspace_id"] = workspace_id
            row["workspace"] = workspace_name
        return merged

    msg_lexical = [_normalize_message_row(r) for r in search_messages(conn, workspace_id=workspace_id, query=q, limit=lexical_limit, use_fts=use_fts, mode="lexical")]
    msg_semantic = [
        _normalize_message_row(r)
        for r in search_messages(
            conn,
            workspace_id=workspace_id,
            query=q,
            limit=lexical_limit,
            mode="semantic",
            model_id=model_id,
            provider=message_embedding_provider,
        )
    ]
    derived_lexical = [_normalize_derived_row(r) for r in search_derived_text(conn, workspace_id=workspace_id, query=q, limit=lexical_limit, derivation_kind=derived_kind, source_kind=derived_source_kind)]
    derived_semantic = [
        _normalize_derived_row(r)
        for r in search_derived_text_semantic(
            conn,
            workspace_id=workspace_id,
            query=q,
            limit=lexical_limit,
            derivation_kind=derived_kind,
            source_kind=derived_source_kind,
            model_id=model_id,
            provider=message_embedding_provider,
        )
    ]

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
    for row in out:
        row["workspace_id"] = workspace_id
        row["workspace"] = workspace_name
    return out


def search_corpus(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    workspace_name: str | None = None,
    query: str,
    limit: int = 20,
    offset: int = 0,
    mode: str = "hybrid",
    model_id: str = "local-hash-128",
    lexical_weight: float = 0.6,
    semantic_weight: float = 0.4,
    semantic_scale: float = 10.0,
    use_fts: bool = True,
    derived_kind: str | None = None,
    derived_source_kind: str | None = None,
    message_embedding_provider: EmbeddingProvider | None = None,
) -> list[dict[str, Any]]:
    slice_limit = max(1, int(limit or 20))
    slice_offset = max(0, int(offset or 0))
    rows = _search_corpus_rows(
        conn,
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        query=query,
        limit=limit,
        offset=offset,
        mode=mode,
        model_id=model_id,
        lexical_weight=lexical_weight,
        semantic_weight=semantic_weight,
        semantic_scale=semantic_scale,
        use_fts=use_fts,
        derived_kind=derived_kind,
        derived_source_kind=derived_source_kind,
        message_embedding_provider=message_embedding_provider,
    )
    return rows[slice_offset : slice_offset + slice_limit]


def search_corpus_page(
    conn: sqlite3.Connection,
    *,
    workspace_id: int,
    workspace_name: str | None = None,
    query: str,
    limit: int = 20,
    offset: int = 0,
    mode: str = "hybrid",
    model_id: str = "local-hash-128",
    lexical_weight: float = 0.6,
    semantic_weight: float = 0.4,
    semantic_scale: float = 10.0,
    use_fts: bool = True,
    derived_kind: str | None = None,
    derived_source_kind: str | None = None,
    message_embedding_provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    page_limit = max(1, int(limit or 20))
    page_offset = max(0, int(offset or 0))
    rows = _search_corpus_rows(
        conn,
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        query=query,
        limit=limit,
        offset=offset,
        mode=mode,
        model_id=model_id,
        lexical_weight=lexical_weight,
        semantic_weight=semantic_weight,
        semantic_scale=semantic_scale,
        use_fts=use_fts,
        derived_kind=derived_kind,
        derived_source_kind=derived_source_kind,
        message_embedding_provider=message_embedding_provider,
    )
    return {
        "results": rows[page_offset : page_offset + page_limit],
        "total": len(rows),
        "limit": page_limit,
        "offset": page_offset,
    }


def _search_corpus_multi_rows(
    conn: sqlite3.Connection,
    *,
    workspaces: list[dict[str, Any]],
    query: str,
    limit: int = 20,
    offset: int = 0,
    mode: str = "hybrid",
    model_id: str = "local-hash-128",
    lexical_weight: float = 0.6,
    semantic_weight: float = 0.4,
    semantic_scale: float = 10.0,
    use_fts: bool = True,
    derived_kind: str | None = None,
    derived_source_kind: str | None = None,
    message_embedding_provider: EmbeddingProvider | None = None,
) -> list[dict[str, Any]]:
    if not workspaces:
        return []
    requested_limit = max(1, int(limit or 20))
    requested_offset = max(0, int(offset or 0))
    per_workspace_limit = max(requested_limit + requested_offset, 10)
    rows: list[dict[str, Any]] = []
    for workspace in workspaces:
        rows.extend(
            _search_corpus_rows(
                conn,
                workspace_id=int(workspace["id"]),
                workspace_name=str(workspace["name"]),
                query=query,
                limit=per_workspace_limit,
                offset=requested_offset,
                mode=mode,
                model_id=model_id,
                lexical_weight=lexical_weight,
                semantic_weight=semantic_weight,
                semantic_scale=semantic_scale,
                use_fts=use_fts,
                derived_kind=derived_kind,
                derived_source_kind=derived_source_kind,
                message_embedding_provider=message_embedding_provider,
            )
        )

    if mode == "lexical":
        rows.sort(key=lambda x: (float(x.get("_score") or 0.0), x.get("sort_ts") or ""), reverse=True)
    elif mode == "semantic":
        rows.sort(key=lambda x: (float(x.get("_semantic_score") or 0.0), x.get("sort_ts") or ""), reverse=True)
    else:
        rows.sort(key=lambda x: (float(x.get("_hybrid_score") or 0.0), x.get("sort_ts") or ""), reverse=True)
    return rows


def search_corpus_multi(
    conn: sqlite3.Connection,
    *,
    workspaces: list[dict[str, Any]],
    query: str,
    limit: int = 20,
    offset: int = 0,
    mode: str = "hybrid",
    model_id: str = "local-hash-128",
    lexical_weight: float = 0.6,
    semantic_weight: float = 0.4,
    semantic_scale: float = 10.0,
    use_fts: bool = True,
    derived_kind: str | None = None,
    derived_source_kind: str | None = None,
    message_embedding_provider: EmbeddingProvider | None = None,
) -> list[dict[str, Any]]:
    slice_limit = max(1, int(limit or 20))
    slice_offset = max(0, int(offset or 0))
    rows = _search_corpus_multi_rows(
        conn,
        workspaces=workspaces,
        query=query,
        limit=limit,
        offset=offset,
        mode=mode,
        model_id=model_id,
        lexical_weight=lexical_weight,
        semantic_weight=semantic_weight,
        semantic_scale=semantic_scale,
        use_fts=use_fts,
        derived_kind=derived_kind,
        derived_source_kind=derived_source_kind,
        message_embedding_provider=message_embedding_provider,
    )
    return rows[slice_offset : slice_offset + slice_limit]


def search_corpus_multi_page(
    conn: sqlite3.Connection,
    *,
    workspaces: list[dict[str, Any]],
    query: str,
    limit: int = 20,
    offset: int = 0,
    mode: str = "hybrid",
    model_id: str = "local-hash-128",
    lexical_weight: float = 0.6,
    semantic_weight: float = 0.4,
    semantic_scale: float = 10.0,
    use_fts: bool = True,
    derived_kind: str | None = None,
    derived_source_kind: str | None = None,
    message_embedding_provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    page_limit = max(1, int(limit or 20))
    page_offset = max(0, int(offset or 0))
    rows = _search_corpus_multi_rows(
        conn,
        workspaces=workspaces,
        query=query,
        limit=limit,
        offset=offset,
        mode=mode,
        model_id=model_id,
        lexical_weight=lexical_weight,
        semantic_weight=semantic_weight,
        semantic_scale=semantic_scale,
        use_fts=use_fts,
        derived_kind=derived_kind,
        derived_source_kind=derived_source_kind,
        message_embedding_provider=message_embedding_provider,
    )
    return {
        "results": rows[page_offset : page_offset + page_limit],
        "total": len(rows),
        "limit": page_limit,
        "offset": page_offset,
    }
