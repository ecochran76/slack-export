#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import sqlite3
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return p.stdout


def extract_json(stdout: str) -> list[dict]:
    start = stdout.find("[")
    end = stdout.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        return json.loads(stdout[start : end + 1])
    except Exception:
        return []


def day_for_ts(ts: str, tz: str) -> str:
    return dt.datetime.fromtimestamp(float(ts), ZoneInfo(tz)).date().isoformat()


def channel_name_to_id(conn: sqlite3.Connection, workspace: str, channel_name: str) -> str | None:
    row = conn.execute(
        """
        select c.channel_id
        from channels c join workspaces w on w.id=c.workspace_id
        where w.name=? and (c.name=? or c.channel_id=?)
        """,
        (workspace, channel_name, channel_name),
    ).fetchone()
    return row[0] if row else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Semantic terms -> full-day channel exports -> single PDF")
    ap.add_argument("--config", default="config.local.yaml")
    ap.add_argument("--db", default="./.local/state/slack_mirror_test.db")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--terms", nargs="+", required=True, help="quoted search terms")
    ap.add_argument("--tz", default="America/Chicago")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--outdir", default="exports/semantic-daypack")
    ap.add_argument("--output-pdf", default="exports/semantic-daypack.pdf")
    ap.add_argument("--embed-attachments", action="store_true")
    ap.add_argument("--attach-files", action="store_true", help="attach source files directly into final PDF")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(args.db)

    bundles: set[tuple[str, str]] = set()  # (channel_name, day)
    for term in args.terms:
        cmd = [
            "slack-mirror",
            "--config",
            args.config,
            "search",
            "semantic",
            "--workspace",
            args.workspace,
            "--query",
            term,
            "--mode",
            "hybrid",
            "--model",
            "local-hash-128",
            "--limit",
            str(args.limit),
            "--json",
        ]
        out = run(cmd)
        rows = extract_json(out)
        for r in rows:
            ch = r.get("channel_name") or r.get("channel_id")
            ts = r.get("ts")
            if not ch or not ts:
                continue
            day = day_for_ts(str(ts), args.tz)
            bundles.add((str(ch), day))

    if not bundles:
        print("No hits found; nothing exported.")
        return 0

    json_exports: list[Path] = []
    for ch_name, day in sorted(bundles):
        slug = ch_name.replace("/", "-")
        out_html = outdir / f"{slug}-{day}.html"
        out_json = outdir / f"{slug}-{day}.json"
        cmd = [
            "python",
            "scripts/export_channel_day.py",
            "--db",
            args.db,
            "--workspace",
            args.workspace,
            "--channel",
            ch_name,
            "--day",
            day,
            "--tz",
            args.tz,
            "--out-html",
            str(out_html),
            "--out-json",
            str(out_json),
        ]
        try:
            run(cmd)
            json_exports.append(out_json)
        except subprocess.CalledProcessError as exc:
            print(f"skip {ch_name} {day}: {exc}")

    if not json_exports:
        print("No channel-day exports succeeded.")
        return 1

    combine_cmd = [
        ".venv/bin/python",
        "scripts/export_multi_day_pdf.py",
        "--inputs",
        *[str(p) for p in json_exports],
        "--output",
        args.output_pdf,
    ]
    if args.embed_attachments:
        combine_cmd.append("--embed-attachments")
    if args.attach_files:
        combine_cmd.append("--attach-files")
    run(combine_cmd)

    print(f"Exported {len(json_exports)} day bundles -> {args.output_pdf}")
    print("Bundles:")
    for p in json_exports:
        print(f"  - {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
