#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from slack_mirror.core.db import apply_migrations, connect, get_workspace_by_name
from slack_mirror.search.dir_adapter import query_directory
from slack_mirror.search.keyword import search_messages


def _dcg(rels: list[int]) -> float:
    out = 0.0
    for i, r in enumerate(rels, start=1):
        out += (2**r - 1) / math.log2(i + 1)
    return out


def _ndcg_at_k(pred: list[str], truth: dict[str, int], k: int) -> float:
    rels = [truth.get(mid, 0) for mid in pred[:k]]
    ideal = sorted(truth.values(), reverse=True)[:k]
    denom = _dcg(ideal)
    if denom <= 0:
        return 0.0
    return _dcg(rels) / denom


def _mrr_at_k(pred: list[str], truth: dict[str, int], k: int) -> float:
    for i, mid in enumerate(pred[:k], start=1):
        if truth.get(mid, 0) > 0:
            return 1.0 / i
    return 0.0


def _dataset_rows(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _eval_slack_db(args: argparse.Namespace, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not args.db or not args.workspace:
        raise SystemExit("--db and --workspace are required for --corpus slack-db")

    conn = connect(args.db)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"))
    ws = get_workspace_by_name(conn, args.workspace)
    if not ws:
        raise SystemExit(f"workspace not found: {args.workspace}")
    workspace_id = int(ws["id"])

    ndcgs: list[float] = []
    mrrs: list[float] = []
    hit3 = 0
    hit10 = 0
    lats: list[float] = []

    for row in rows:
        query = row["query"]
        truth = row.get("relevant", {})

        t0 = time.perf_counter()
        found = search_messages(
            conn,
            workspace_id=workspace_id,
            query=query,
            limit=args.limit,
            mode=args.mode,
            model_id=args.model,
        )
        lat_ms = (time.perf_counter() - t0) * 1000.0

        pred = []
        for r in found:
            pred.append(f"{r.get('channel_id')}:{r.get('ts')}")
            if r.get("channel_name"):
                pred.append(f"{r.get('channel_name')}:{r.get('ts')}")
        ndcgs.append(_ndcg_at_k(pred, truth, args.limit))
        mrrs.append(_mrr_at_k(pred, truth, args.limit))
        hit3 += 1 if any(truth.get(x, 0) > 0 for x in pred[:3]) else 0
        hit10 += 1 if any(truth.get(x, 0) > 0 for x in pred[:10]) else 0
        lats.append(lat_ms)

    total = len(rows)
    return {
        "corpus": "slack-db",
        "queries": total,
        "mode": args.mode,
        "ndcg_at_k": round(sum(ndcgs) / total, 6),
        "mrr_at_k": round(sum(mrrs) / total, 6),
        "hit_at_3": round(hit3 / total, 6),
        "hit_at_10": round(hit10 / total, 6),
        "latency_ms_p50": round(statistics.median(lats), 3),
        "latency_ms_p95": round(sorted(lats)[max(0, math.ceil(total * 0.95) - 1)], 3),
    }


def _eval_dir(args: argparse.Namespace, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not args.path:
        raise SystemExit("--path is required for --corpus dir")

    ndcgs: list[float] = []
    mrrs: list[float] = []
    hit3 = 0
    hit10 = 0
    lats: list[float] = []

    for row in rows:
        query = row["query"]
        truth = row.get("relevant", {})

        t0 = time.perf_counter()
        found = query_directory(
            root=args.path,
            query=query,
            mode=args.mode,
            glob=args.glob,
            limit=args.limit,
        )
        lat_ms = (time.perf_counter() - t0) * 1000.0

        pred = [str(r.get("path") or "") for r in found]
        ndcgs.append(_ndcg_at_k(pred, truth, args.limit))
        mrrs.append(_mrr_at_k(pred, truth, args.limit))
        hit3 += 1 if any(truth.get(x, 0) > 0 for x in pred[:3]) else 0
        hit10 += 1 if any(truth.get(x, 0) > 0 for x in pred[:10]) else 0
        lats.append(lat_ms)

    total = len(rows)
    return {
        "corpus": "dir",
        "queries": total,
        "mode": args.mode,
        "glob": args.glob,
        "ndcg_at_k": round(sum(ndcgs) / total, 6),
        "mrr_at_k": round(sum(mrrs) / total, 6),
        "hit_at_3": round(hit3 / total, 6),
        "hit_at_10": round(hit10 / total, 6),
        "latency_ms_p50": round(statistics.median(lats), 3),
        "latency_ms_p95": round(sorted(lats)[max(0, math.ceil(total * 0.95) - 1)], 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Portable eval for lexical/semantic/hybrid search")
    ap.add_argument("--dataset", required=True, help="JSONL of {query, relevant:{id:grade}}")
    ap.add_argument("--corpus", choices=["slack-db", "dir"], default="slack-db")
    ap.add_argument("--mode", choices=["lexical", "semantic", "hybrid"], default="hybrid")
    ap.add_argument("--limit", type=int, default=10)

    # slack-db options
    ap.add_argument("--db", help="sqlite db path (required for slack-db)")
    ap.add_argument("--workspace", help="workspace name (required for slack-db)")
    ap.add_argument("--model", default="local-hash-128")

    # dir options
    ap.add_argument("--path", help="directory root (required for dir)")
    ap.add_argument("--glob", default="**/*.md", help="file glob for dir corpus")

    args = ap.parse_args()
    rows = _dataset_rows(args.dataset)
    if not rows:
        raise SystemExit("dataset is empty")

    if args.corpus == "slack-db":
        report = _eval_slack_db(args, rows)
    else:
        report = _eval_dir(args, rows)

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
