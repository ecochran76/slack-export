from __future__ import annotations

import sqlite3
import shlex
from typing import Any

from slack_mirror.search.embeddings import EmbeddingProvider
from slack_mirror.search.derived_text import search_derived_text, search_derived_text_semantic
from slack_mirror.search.keyword import search_messages
from slack_mirror.search.rerankers import RerankerProvider, rerank_rows

FUSION_WEIGHTED = "weighted"
FUSION_RRF = "rrf"
DEFAULT_RRF_K = 60.0

MESSAGE_LANE_OPERATOR_PREFIXES = (
    "from:",
    "participant:",
    "user:",
    "in:",
    "channel:",
    "source:",
    "before:",
    "after:",
    "since:",
    "until:",
    "on:",
    "has:",
    "is:",
)


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


def _normalize_fusion_method(value: str | None) -> str:
    method = (value or FUSION_WEIGHTED).strip().lower().replace("_", "-")
    if method in {"weighted", "weighted-score", "score"}:
        return FUSION_WEIGHTED
    if method in {"rrf", "reciprocal-rank", "reciprocal-rank-fusion"}:
        return FUSION_RRF
    raise ValueError(f"Unsupported corpus fusion method: {value}")


def _has_message_lane_operator(query: str) -> bool:
    try:
        tokens = shlex.split(query or "")
    except ValueError:
        tokens = (query or "").split()
    for token in tokens:
        stripped = token[1:] if token.startswith("-") else token
        lowered = stripped.lower()
        if any(lowered.startswith(prefix) for prefix in MESSAGE_LANE_OPERATOR_PREFIXES):
            return True
    return False


def _rank_by_key(rows: list[dict[str, Any]], key_fn) -> dict[tuple[str, str], int]:
    ranks: dict[tuple[str, str], int] = {}
    for index, row in enumerate(rows, start=1):
        ranks.setdefault(key_fn(row), index)
    return ranks


def _attach_explain(
    row: dict[str, Any],
    *,
    mode: str,
    fusion_method: str | None = None,
    lexical_weight: float | None = None,
    semantic_weight: float | None = None,
    semantic_scale: float | None = None,
) -> dict[str, Any]:
    row["_explain"] = {
        "mode": mode,
        "source": row.get("_source"),
        "fusion_method": fusion_method,
        "scores": {
            "lexical": row.get("_lexical_score", row.get("_score")),
            "semantic": row.get("_semantic_score"),
            "hybrid": row.get("_hybrid_score"),
            "rerank": row.get("_rerank_score"),
        },
        "ranks": {
            "lexical": row.get("_lexical_rank"),
            "semantic": row.get("_semantic_rank"),
        },
        "weights": {
            "lexical": lexical_weight,
            "semantic": semantic_weight,
            "semantic_scale": semantic_scale,
        },
        "rerank_provider": row.get("_rerank_provider"),
    }
    return row


def _stable_part(value: Any) -> str:
    return str(value or "").replace("|", "%7C")


def _attach_action_target(row: dict[str, Any], *, workspace_id: int, workspace_name: str | None) -> dict[str, Any]:
    result_kind = str(row.get("result_kind") or "")
    if result_kind == "message":
        channel_id = str(row.get("channel_id") or "")
        ts = str(row.get("ts") or "")
        target_id = f"message|{_stable_part(workspace_name or workspace_id)}|{_stable_part(channel_id)}|{_stable_part(ts)}"
        row["action_target"] = {
            "version": 1,
            "kind": "message",
            "id": target_id,
            "workspace": workspace_name,
            "workspace_id": workspace_id,
            "channel_id": channel_id,
            "channel_name": row.get("channel_name"),
            "ts": ts,
            "thread_ts": row.get("thread_ts"),
            "user_id": row.get("user_id"),
            "selection_label": f"{workspace_name or workspace_id}:{channel_id}:{ts}",
        }
        return row

    if result_kind == "derived_text":
        source_kind = str(row.get("source_kind") or "")
        source_id = str(row.get("source_id") or "")
        derivation_kind = str(row.get("derivation_kind") or "")
        extractor = str(row.get("extractor") or "")
        chunk_index = row.get("chunk_index")
        target_id = (
            f"derived_text|{_stable_part(workspace_name or workspace_id)}|{_stable_part(source_kind)}|"
            f"{_stable_part(source_id)}|{_stable_part(derivation_kind)}|{_stable_part(extractor)}"
        )
        if chunk_index is not None:
            target_id = f"{target_id}|chunk:{_stable_part(chunk_index)}"
        row["action_target"] = {
            "version": 1,
            "kind": "derived_text",
            "id": target_id,
            "workspace": workspace_name,
            "workspace_id": workspace_id,
            "derived_text_id": row.get("id"),
            "source_kind": source_kind,
            "source_id": source_id,
            "source_label": row.get("source_label"),
            "derivation_kind": derivation_kind,
            "extractor": extractor,
            "chunk_index": chunk_index,
            "start_offset": row.get("start_offset"),
            "end_offset": row.get("end_offset"),
            "selection_label": f"{workspace_name or workspace_id}:{source_kind}:{source_id}",
        }
    return row


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
    fusion_method: str = FUSION_WEIGHTED,
    use_fts: bool = True,
    derived_kind: str | None = None,
    derived_source_kind: str | None = None,
    message_embedding_provider: EmbeddingProvider | None = None,
    rerank: bool = False,
    rerank_top_n: int = 50,
    reranker_provider: RerankerProvider | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    mode = (mode or "hybrid").lower()
    normalized_fusion_method = _normalize_fusion_method(fusion_method)
    requested_limit = max(1, int(limit or 20))
    requested_offset = max(0, int(offset or 0))
    lexical_limit = max((requested_limit + requested_offset) * 2, 20)
    include_derived_text = not _has_message_lane_operator(q)

    if mode == "lexical":
        msg_rows = [_normalize_message_row(r) for r in search_messages(conn, workspace_id=workspace_id, query=q, limit=lexical_limit, use_fts=use_fts, mode="lexical")]
        derived_rows = (
            [
                _normalize_derived_row(r)
                for r in search_derived_text(
                    conn,
                    workspace_id=workspace_id,
                    query=q,
                    limit=lexical_limit,
                    derivation_kind=derived_kind,
                    source_kind=derived_source_kind,
                )
            ]
            if include_derived_text
            else []
        )
        merged = msg_rows + derived_rows
        merged.sort(key=lambda x: (float(x.get("_score") or 0.0), x.get("sort_ts") or ""), reverse=True)
        for row in merged:
            row["workspace_id"] = workspace_id
            row["workspace"] = workspace_name
            _attach_action_target(row, workspace_id=workspace_id, workspace_name=workspace_name)
            _attach_explain(row, mode="lexical")
        if rerank:
            merged = rerank_rows(merged, query=q, top_n=rerank_top_n, provider=reranker_provider)
            for row in merged:
                _attach_action_target(row, workspace_id=workspace_id, workspace_name=workspace_name)
                _attach_explain(row, mode="lexical")
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
        derived_rows = (
            [
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
            if include_derived_text
            else []
        )
        merged = msg_rows + derived_rows
        merged.sort(key=lambda x: (float(x.get("_semantic_score") or 0.0), x.get("sort_ts") or ""), reverse=True)
        for row in merged:
            row["workspace_id"] = workspace_id
            row["workspace"] = workspace_name
            _attach_action_target(row, workspace_id=workspace_id, workspace_name=workspace_name)
            _attach_explain(row, mode="semantic")
        if rerank:
            merged = rerank_rows(merged, query=q, top_n=rerank_top_n, provider=reranker_provider)
            for row in merged:
                _attach_action_target(row, workspace_id=workspace_id, workspace_name=workspace_name)
                _attach_explain(row, mode="semantic")
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
    derived_lexical = (
        [
            _normalize_derived_row(r)
            for r in search_derived_text(
                conn,
                workspace_id=workspace_id,
                query=q,
                limit=lexical_limit,
                derivation_kind=derived_kind,
                source_kind=derived_source_kind,
            )
        ]
        if include_derived_text
        else []
    )
    derived_semantic = (
        [
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
        if include_derived_text
        else []
    )
    lexical_ranks = _rank_by_key(msg_lexical, _message_key)
    lexical_ranks.update(_rank_by_key(derived_lexical, _derived_key))
    semantic_ranks = _rank_by_key(msg_semantic, _message_key)
    semantic_ranks.update(_rank_by_key(derived_semantic, _derived_key))

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in msg_lexical:
        key = _message_key(row)
        merged[key] = {
            **row,
            "_lexical_score": float(row.get("_score") or 0.0),
            "_semantic_score": 0.0,
            "_lexical_rank": lexical_ranks.get(key),
            "_semantic_rank": None,
            "_source": "lexical",
        }
    for row in derived_lexical:
        key = _derived_key(row)
        merged[key] = {
            **row,
            "_lexical_score": float(row.get("_score") or 0.0),
            "_semantic_score": 0.0,
            "_lexical_rank": lexical_ranks.get(key),
            "_semantic_rank": None,
            "_source": "lexical",
        }

    for row in msg_semantic:
        key = _message_key(row)
        if key in merged:
            merged[key]["_semantic_score"] = float(row.get("_semantic_score") or 0.0)
            merged[key]["_semantic_rank"] = semantic_ranks.get(key)
            merged[key]["_source"] = "hybrid"
        else:
            merged[key] = {
                **row,
                "_lexical_score": 0.0,
                "_semantic_score": float(row.get("_semantic_score") or 0.0),
                "_lexical_rank": None,
                "_semantic_rank": semantic_ranks.get(key),
                "_source": "semantic",
            }

    for row in derived_semantic:
        key = _derived_key(row)
        if key in merged:
            merged[key]["_semantic_score"] = float(row.get("_semantic_score") or 0.0)
            merged[key]["_semantic_rank"] = semantic_ranks.get(key)
            merged[key]["_source"] = "hybrid"
        else:
            merged[key] = {
                **row,
                "_lexical_score": 0.0,
                "_semantic_score": float(row.get("_semantic_score") or 0.0),
                "_lexical_rank": None,
                "_semantic_rank": semantic_ranks.get(key),
                "_source": "semantic",
            }

    for row in merged.values():
        if normalized_fusion_method == FUSION_RRF:
            lexical_rank = row.get("_lexical_rank")
            semantic_rank = row.get("_semantic_rank")
            lexical_component = (lexical_weight / (DEFAULT_RRF_K + float(lexical_rank))) if lexical_rank else 0.0
            semantic_component = (semantic_weight / (DEFAULT_RRF_K + float(semantic_rank))) if semantic_rank else 0.0
            row["_hybrid_score"] = round(lexical_component + semantic_component, 6)
        else:
            row["_hybrid_score"] = round(
                (lexical_weight * float(row.get("_lexical_score") or 0.0))
                + (semantic_weight * float(row.get("_semantic_score") or 0.0) * semantic_scale),
                6,
            )
        row["_fusion_method"] = normalized_fusion_method
        _attach_explain(
            row,
            mode="hybrid",
            fusion_method=normalized_fusion_method,
            lexical_weight=lexical_weight,
            semantic_weight=semantic_weight,
            semantic_scale=semantic_scale,
        )

    out = sorted(
        merged.values(),
        key=lambda x: (float(x.get("_hybrid_score") or 0.0), x.get("sort_ts") or ""),
        reverse=True,
    )
    for row in out:
        row["workspace_id"] = workspace_id
        row["workspace"] = workspace_name
        _attach_action_target(row, workspace_id=workspace_id, workspace_name=workspace_name)
    if rerank:
        out = rerank_rows(out, query=q, top_n=rerank_top_n, provider=reranker_provider)
        for row in out:
            _attach_action_target(row, workspace_id=workspace_id, workspace_name=workspace_name)
            _attach_explain(
                row,
                mode="hybrid",
                fusion_method=normalized_fusion_method,
                lexical_weight=lexical_weight,
                semantic_weight=semantic_weight,
                semantic_scale=semantic_scale,
            )
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
    fusion_method: str = FUSION_WEIGHTED,
    use_fts: bool = True,
    derived_kind: str | None = None,
    derived_source_kind: str | None = None,
    message_embedding_provider: EmbeddingProvider | None = None,
    rerank: bool = False,
    rerank_top_n: int = 50,
    reranker_provider: RerankerProvider | None = None,
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
        fusion_method=fusion_method,
        use_fts=use_fts,
        derived_kind=derived_kind,
        derived_source_kind=derived_source_kind,
        message_embedding_provider=message_embedding_provider,
        rerank=rerank,
        rerank_top_n=rerank_top_n,
        reranker_provider=reranker_provider,
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
    fusion_method: str = FUSION_WEIGHTED,
    use_fts: bool = True,
    derived_kind: str | None = None,
    derived_source_kind: str | None = None,
    message_embedding_provider: EmbeddingProvider | None = None,
    rerank: bool = False,
    rerank_top_n: int = 50,
    reranker_provider: RerankerProvider | None = None,
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
        fusion_method=fusion_method,
        use_fts=use_fts,
        derived_kind=derived_kind,
        derived_source_kind=derived_source_kind,
        message_embedding_provider=message_embedding_provider,
        rerank=rerank,
        rerank_top_n=rerank_top_n,
        reranker_provider=reranker_provider,
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
    fusion_method: str = FUSION_WEIGHTED,
    use_fts: bool = True,
    derived_kind: str | None = None,
    derived_source_kind: str | None = None,
    message_embedding_provider: EmbeddingProvider | None = None,
    rerank: bool = False,
    rerank_top_n: int = 50,
    reranker_provider: RerankerProvider | None = None,
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
                fusion_method=fusion_method,
                use_fts=use_fts,
                derived_kind=derived_kind,
                derived_source_kind=derived_source_kind,
                message_embedding_provider=message_embedding_provider,
                rerank=False,
            )
        )

    if mode == "lexical":
        rows.sort(key=lambda x: (float(x.get("_score") or 0.0), x.get("sort_ts") or ""), reverse=True)
    elif mode == "semantic":
        rows.sort(key=lambda x: (float(x.get("_semantic_score") or 0.0), x.get("sort_ts") or ""), reverse=True)
    else:
        rows.sort(key=lambda x: (float(x.get("_hybrid_score") or 0.0), x.get("sort_ts") or ""), reverse=True)
    if rerank:
        rows = rerank_rows(rows, query=query, top_n=rerank_top_n, provider=reranker_provider)
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
    fusion_method: str = FUSION_WEIGHTED,
    use_fts: bool = True,
    derived_kind: str | None = None,
    derived_source_kind: str | None = None,
    message_embedding_provider: EmbeddingProvider | None = None,
    rerank: bool = False,
    rerank_top_n: int = 50,
    reranker_provider: RerankerProvider | None = None,
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
        fusion_method=fusion_method,
        use_fts=use_fts,
        derived_kind=derived_kind,
        derived_source_kind=derived_source_kind,
        message_embedding_provider=message_embedding_provider,
        rerank=rerank,
        rerank_top_n=rerank_top_n,
        reranker_provider=reranker_provider,
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
    fusion_method: str = FUSION_WEIGHTED,
    use_fts: bool = True,
    derived_kind: str | None = None,
    derived_source_kind: str | None = None,
    message_embedding_provider: EmbeddingProvider | None = None,
    rerank: bool = False,
    rerank_top_n: int = 50,
    reranker_provider: RerankerProvider | None = None,
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
        fusion_method=fusion_method,
        use_fts=use_fts,
        derived_kind=derived_kind,
        derived_source_kind=derived_source_kind,
        message_embedding_provider=message_embedding_provider,
        rerank=rerank,
        rerank_top_n=rerank_top_n,
        reranker_provider=reranker_provider,
    )
    return {
        "results": rows[page_offset : page_offset + page_limit],
        "total": len(rows),
        "limit": page_limit,
        "offset": page_offset,
    }
