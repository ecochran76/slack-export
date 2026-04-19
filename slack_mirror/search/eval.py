from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from slack_mirror.search.corpus import search_corpus
from slack_mirror.search.embeddings import EmbeddingProvider
from slack_mirror.search.keyword import search_messages


def dcg(rels: list[int]) -> float:
    out = 0.0
    for i, r in enumerate(rels, start=1):
        out += (2**r - 1) / math.log2(i + 1)
    return out


def ndcg_at_k(pred: list[str], truth: dict[str, int], k: int) -> float:
    rels = [truth.get(mid, 0) for mid in pred[:k]]
    ideal = sorted(truth.values(), reverse=True)[:k]
    denom = dcg(ideal)
    if denom <= 0:
        return 0.0
    return dcg(rels) / denom


def mrr_at_k(pred: list[str], truth: dict[str, int], k: int) -> float:
    for i, mid in enumerate(pred[:k], start=1):
        if truth.get(mid, 0) > 0:
            return 1.0 / i
    return 0.0


def dataset_rows(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _summarize_report(
    *,
    corpus: str,
    mode: str,
    total: int,
    ndcgs: list[float],
    mrrs: list[float],
    hit3: int,
    hit10: int,
    lats: list[float],
    query_reports: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = {
        "corpus": corpus,
        "queries": total,
        "mode": mode,
        "ndcg_at_k": round(sum(ndcgs) / total, 6),
        "mrr_at_k": round(sum(mrrs) / total, 6),
        "hit_at_3": round(hit3 / total, 6),
        "hit_at_10": round(hit10 / total, 6),
        "latency_ms_p50": round(statistics.median(lats), 3),
        "latency_ms_p95": round(sorted(lats)[max(0, math.ceil(total * 0.95) - 1)], 3),
        "query_reports": query_reports or [],
    }
    if extra:
        report.update(extra)
    return report


def evaluate_message_search(
    conn,
    *,
    workspace_id: int,
    dataset: list[dict[str, Any]],
    mode: str,
    limit: int = 10,
    model_id: str = "local-hash-128",
    embedding_provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    ndcgs: list[float] = []
    mrrs: list[float] = []
    hit3 = 0
    hit10 = 0
    lats: list[float] = []
    query_reports: list[dict[str, Any]] = []

    for row in dataset:
        query = row["query"]
        truth = row.get("relevant", {})

        t0 = time.perf_counter()
        found = search_messages(
            conn,
            workspace_id=workspace_id,
            query=query,
            limit=limit,
            mode=mode,
            model_id=model_id,
            provider=embedding_provider,
        )
        lat_ms = (time.perf_counter() - t0) * 1000.0

        pred = []
        for r in found:
            pred.append(f"{r.get('channel_id')}:{r.get('ts')}")
            if r.get("channel_name"):
                pred.append(f"{r.get('channel_name')}:{r.get('ts')}")
        ndcgs.append(ndcg_at_k(pred, truth, limit))
        mrrs.append(mrr_at_k(pred, truth, limit))
        query_hit3 = 1 if any(truth.get(x, 0) > 0 for x in pred[:3]) else 0
        query_hit10 = 1 if any(truth.get(x, 0) > 0 for x in pred[:10]) else 0
        hit3 += query_hit3
        hit10 += query_hit10
        lats.append(lat_ms)
        query_reports.append(
            {
                "query": query,
                "ndcg_at_k": round(ndcgs[-1], 6),
                "mrr_at_k": round(mrrs[-1], 6),
                "hit_at_3": bool(query_hit3),
                "hit_at_10": bool(query_hit10),
                "latency_ms": round(lat_ms, 3),
                "top_results": pred[: min(limit, 10)],
            }
        )

    return _summarize_report(
        corpus="slack-db",
        mode=mode,
        total=len(dataset),
        ndcgs=ndcgs,
        mrrs=mrrs,
        hit3=hit3,
        hit10=hit10,
        lats=lats,
        query_reports=query_reports,
    )


def evaluate_corpus_search(
    conn,
    *,
    workspace_id: int,
    dataset: list[dict[str, Any]],
    mode: str,
    limit: int = 10,
    model_id: str = "local-hash-128",
    embedding_provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    ndcgs: list[float] = []
    mrrs: list[float] = []
    hit3 = 0
    hit10 = 0
    lats: list[float] = []
    query_reports: list[dict[str, Any]] = []

    for row in dataset:
        query = row["query"]
        truth = row.get("relevant", {})

        t0 = time.perf_counter()
        found = search_corpus(
            conn,
            workspace_id=workspace_id,
            query=query,
            limit=limit,
            mode=mode,
            model_id=model_id,
            message_embedding_provider=embedding_provider,
        )
        lat_ms = (time.perf_counter() - t0) * 1000.0

        pred: list[str] = []
        for r in found:
            if r.get("result_kind") == "message":
                pred.append(f"{r.get('channel_id')}:{r.get('ts')}")
                if r.get("channel_name"):
                    pred.append(f"{r.get('channel_name')}:{r.get('ts')}")
            else:
                pred.append(
                    f"{r.get('source_kind')}:{r.get('source_id')}:{r.get('derivation_kind')}:{r.get('extractor')}"
                )
                if r.get("source_label"):
                    pred.append(str(r.get("source_label")))
        ndcgs.append(ndcg_at_k(pred, truth, limit))
        mrrs.append(mrr_at_k(pred, truth, limit))
        query_hit3 = 1 if any(truth.get(x, 0) > 0 for x in pred[:3]) else 0
        query_hit10 = 1 if any(truth.get(x, 0) > 0 for x in pred[:10]) else 0
        hit3 += query_hit3
        hit10 += query_hit10
        lats.append(lat_ms)
        query_reports.append(
            {
                "query": query,
                "ndcg_at_k": round(ndcgs[-1], 6),
                "mrr_at_k": round(mrrs[-1], 6),
                "hit_at_3": bool(query_hit3),
                "hit_at_10": bool(query_hit10),
                "latency_ms": round(lat_ms, 3),
                "top_results": pred[: min(limit, 10)],
            }
        )

    return _summarize_report(
        corpus="slack-corpus",
        mode=mode,
        total=len(dataset),
        ndcgs=ndcgs,
        mrrs=mrrs,
        hit3=hit3,
        hit10=hit10,
        lats=lats,
        query_reports=query_reports,
    )
