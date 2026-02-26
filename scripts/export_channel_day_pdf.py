#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
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
    ap.add_argument("--embed-attachments", action="store_true", help="embed image attachments directly into PDF when local_path exists")
    args = ap.parse_args()

    data = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    out = Path(args.output_pdf)
    out.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out), pagesize=letter)
    w, h = letter
    y = h - 40

    def line(s: str, size: int = 10, gap: int = 14, x: int = 40):
        nonlocal y, c
        if y < 50:
            c.showPage()
            y = h - 40
        c.setFont("Helvetica", size)
        c.drawString(x, y, s[:180])
        y -= gap

    def draw_image(path: str, x: int, max_width: float = 252.0):
        nonlocal y, c
        try:
            img = ImageReader(path)
            iw, ih = img.getSize()
            if iw <= 0 or ih <= 0:
                return
            scale = min(max_width / float(iw), 1.0)
            dw = float(iw) * scale
            dh = float(ih) * scale
            if y - dh < 50:
                c.showPage()
                y = h - 40
            c.drawImage(img, x, y - dh, width=dw, height=dh, preserveAspectRatio=True, mask='auto')
            y -= dh + 8
        except Exception:
            return

    line(f"Workspace: {data.get('workspace')}", 12, 16)
    line(f"Channel: #{data.get('channel')} ({data.get('channel_id')})", 12, 16)
    line(f"Day: {data.get('day')} ({data.get('tz')})", 12, 16)
    line(f"Exported: {dt.datetime.now().isoformat(timespec='seconds')}", 10, 18)
    line("-" * 100, 9, 12)

    for m in data.get("messages", []):
        is_reply = bool(m.get("thread_ts")) and str(m.get("thread_ts")) != str(m.get("ts"))
        x = 90 if is_reply else 40
        meta = f"[{m.get('human_ts') or m.get('ts')}] {m.get('user_label') or m.get('user_id') or 'unknown'}"
        if m.get("thread_ts"):
            meta += f" thread={m.get('thread_ts')}"
        if m.get("deleted"):
            meta += " deleted"
        if is_reply:
            line("[THREAD REPLY]", 8, 10, x=x)
        line(meta, 9, 12, x=x)
        for l in wrap(m.get("text") or "", 116):
            line("  " + l, 9, 11, x=x)
        atts = m.get("attachments") or []
        if atts:
            line("  attachments:", 9, 11, x=x)
            for a in atts:
                link = a.get("local_path") or a.get("permalink") or ""
                line(f"    - {a.get('name') or a.get('id')} {link}", 8, 10, x=x)
                if args.embed_attachments and (a.get("mimetype") or "").lower().startswith("image/") and a.get("local_path"):
                    draw_image(str(a.get("local_path")), x=x + 10, max_width=252.0)
        line("", 9, 8, x=x)

    c.save()
    print(f"Wrote PDF: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
