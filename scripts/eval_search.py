#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from slack_mirror.core.config import load_config
from slack_mirror.core.db import apply_migrations, connect, get_workspace_by_name
from slack_mirror.search.embeddings import build_embedding_provider
from slack_mirror.search.eval import dataset_rows, evaluate_corpus_search, evaluate_message_search, mrr_at_k as _mrr_at_k, ndcg_at_k as _ndcg_at_k
from slack_mirror.search.dir_adapter import query_directory


def _eval_slack_db(args: argparse.Namespace, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not args.db or not args.workspace:
        raise SystemExit("--db and --workspace are required for --corpus slack-db")

    conn = connect(args.db)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"))
    ws = get_workspace_by_name(conn, args.workspace)
    if not ws:
        raise SystemExit(f"workspace not found: {args.workspace}")
    provider = None
    if args.config:
        cfg = load_config(args.config)
        provider = build_embedding_provider(cfg.data)
    return evaluate_message_search(
        conn,
        workspace_id=int(ws["id"]),
        dataset=rows,
        mode=args.mode,
        limit=args.limit,
        model_id=args.model,
        embedding_provider=provider,
    )


def _eval_slack_corpus(args: argparse.Namespace, rows: list[dict[str, object]]) -> dict[str, object]:
    if not args.db or not args.workspace:
        raise SystemExit("--db and --workspace are required for --corpus slack-corpus")

    conn = connect(args.db)
    apply_migrations(conn, str(Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"))
    ws = get_workspace_by_name(conn, args.workspace)
    if not ws:
        raise SystemExit(f"workspace not found: {args.workspace}")
    provider = None
    if args.config:
        cfg = load_config(args.config)
        provider = build_embedding_provider(cfg.data)
    return evaluate_corpus_search(
        conn,
        workspace_id=int(ws["id"]),
        dataset=rows,
        mode=args.mode,
        limit=args.limit,
        model_id=args.model,
        embedding_provider=provider,
    )


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
    ap.add_argument("--corpus", choices=["slack-db", "slack-corpus", "dir"], default="slack-db")
    ap.add_argument("--mode", choices=["lexical", "semantic", "hybrid"], default="hybrid")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--config", help="optional config path used to resolve the semantic provider")

    # slack-db options
    ap.add_argument("--db", help="sqlite db path (required for slack-db)")
    ap.add_argument("--workspace", help="workspace name (required for slack-db)")
    ap.add_argument("--model", default="local-hash-128")

    # dir options
    ap.add_argument("--path", help="directory root (required for dir)")
    ap.add_argument("--glob", default="**/*.md", help="file glob for dir corpus")

    args = ap.parse_args()
    rows = dataset_rows(args.dataset)
    if not rows:
        raise SystemExit("dataset is empty")

    if args.corpus == "slack-db":
        report = _eval_slack_db(args, rows)
    elif args.corpus == "slack-corpus":
        report = _eval_slack_corpus(args, rows)
    else:
        report = _eval_dir(args, rows)

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
