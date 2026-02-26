#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def wrap(text: str, width: int = 110) -> list[str]:
    out: list[str] = []
    for para in (text or "").splitlines() or [""]:
        s = para.strip()
        if not s:
            out.append("")
            continue
        while len(s) > width:
            cut = s.rfind(" ", 0, width)
            if cut <= 0:
                cut = width
            out.append(s[:cut])
            s = s[cut:].strip()
        out.append(s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Render exported channel-day JSON to PDF")
    ap.add_argument("--input-json", required=True)
    ap.add_argument("--output-pdf", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    out = Path(args.output_pdf)
    out.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out), pagesize=letter)
    w, h = letter
    y = h - 40

    def line(s: str, size: int = 10, gap: int = 14):
        nonlocal y, c
        if y < 50:
            c.showPage()
            y = h - 40
        c.setFont("Helvetica", size)
        c.drawString(40, y, s[:160])
        y -= gap

    line(f"Workspace: {data.get('workspace')}", 12, 16)
    line(f"Channel: #{data.get('channel')} ({data.get('channel_id')})", 12, 16)
    line(f"Day: {data.get('day')} ({data.get('tz')})", 12, 16)
    line(f"Exported: {dt.datetime.now().isoformat(timespec='seconds')}", 10, 18)
    line("-" * 100, 9, 12)

    for m in data.get("messages", []):
        meta = f"[{m.get('ts')}] {m.get('user_id') or 'unknown'}"
        if m.get("thread_ts"):
            meta += f" thread={m.get('thread_ts')}"
        if m.get("deleted"):
            meta += " deleted"
        line(meta, 9, 12)
        for l in wrap(m.get("text") or "", 120):
            line("  " + l, 9, 11)
        atts = m.get("attachments") or []
        if atts:
            line("  attachments:", 9, 11)
            for a in atts:
                link = a.get("local_path") or a.get("permalink") or ""
                line(f"    - {a.get('name') or a.get('id')} {link}", 8, 10)
        line("", 9, 8)

    c.save()
    print(f"Wrote PDF: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
