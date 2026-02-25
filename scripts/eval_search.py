#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path

from slack_mirror.core.db import apply_migrations, connect, get_workspace_by_name
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate lexical/semantic/hybrid search quality + latency")
    ap.add_argument("--db", required=True)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--dataset", required=True, help="JSONL of {query, relevant:{'C1:123.45':2}}")
    ap.add_argument("--mode", choices=["lexical", "semantic", "hybrid"], default="hybrid")
    ap.add_argument("--model", default="local-hash-128")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

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
    total = 0

    for line in Path(args.dataset).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        query = row["query"]
        truth = row.get("relevant", {})

        t0 = time.perf_counter()
        rows = search_messages(
            conn,
            workspace_id=workspace_id,
            query=query,
            limit=args.limit,
            mode=args.mode,
            model_id=args.model,
        )
        lat_ms = (time.perf_counter() - t0) * 1000.0

        pred = [f"{r.get('channel_id')}:{r.get('ts')}" for r in rows]
        ndcgs.append(_ndcg_at_k(pred, truth, args.limit))
        mrrs.append(_mrr_at_k(pred, truth, args.limit))
        hit3 += 1 if any(truth.get(x, 0) > 0 for x in pred[:3]) else 0
        hit10 += 1 if any(truth.get(x, 0) > 0 for x in pred[:10]) else 0
        lats.append(lat_ms)
        total += 1

    if total == 0:
        raise SystemExit("dataset is empty")

    print(json.dumps(
        {
            "queries": total,
            "mode": args.mode,
            "ndcg_at_k": round(sum(ndcgs) / total, 6),
            "mrr_at_k": round(sum(mrrs) / total, 6),
            "hit_at_3": round(hit3 / total, 6),
            "hit_at_10": round(hit10 / total, 6),
            "latency_ms_p50": round(statistics.median(lats), 3),
            "latency_ms_p95": round(sorted(lats)[max(0, math.ceil(total * 0.95) - 1)], 3),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
