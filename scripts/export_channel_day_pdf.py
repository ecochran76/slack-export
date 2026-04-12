#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter


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


def attachment_link(attachment: dict) -> str:
    for key in ("public_url", "download_url", "permalink", "local_path"):
        value = attachment.get(key) or ""
        if value:
            return str(value)
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Render exported channel-day JSON to PDF")
    ap.add_argument("--input-json", required=True)
    ap.add_argument("--output-pdf", required=True)
    ap.add_argument("--embed-attachments", action="store_true", help="embed image attachments directly into PDF when local_path exists")
    ap.add_argument("--attach-files", action="store_true", help="attach source files to the PDF as embedded attachments")
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
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", size)
        c.drawString(x, y, s[:180])
        y -= gap

    speaker_colors = [
        (0.0, 0.0, 0.0),      # black
        (0.05, 0.18, 0.45),    # dark blue
        (0.0, 0.35, 0.1),      # dark green
        (0.35, 0.12, 0.45),    # dark purple
        (0.45, 0.2, 0.0),      # dark orange/brown
        (0.35, 0.0, 0.0),      # dark red
    ]
    speaker_index: dict[str, int] = {}

    def line_meta(s: str, speaker_key: str, gap: int = 12, x: int = 40):
        nonlocal y, c
        if y < 50:
            c.showPage()
            y = h - 40
        idx = speaker_index.setdefault(speaker_key, len(speaker_index))
        r, g, b = speaker_colors[idx % len(speaker_colors)]
        c.setFillColorRGB(r, g, b)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, s[:180])
        c.setFillColorRGB(0, 0, 0)
        y -= gap

    def line_link(label: str, url: str, size: int = 9, gap: int = 12, x: int = 40):
        nonlocal y, c
        if y < 50:
            c.showPage()
            y = h - 40
        txt = ("🔗 " + label)[:180]
        c.setFillColorRGB(0.02, 0.29, 0.77)
        c.setFont("Helvetica-Bold", size)
        c.drawString(x, y, txt)
        width = c.stringWidth(txt, "Helvetica-Bold", size)
        c.setLineWidth(0.8)
        c.setStrokeColorRGB(0.02, 0.29, 0.77)
        c.line(x, y - 1, x + width, y - 1)
        c.setFillColorRGB(0, 0, 0)
        try:
            c.linkURL(url, (x, y - 3, x + width, y + size + 2), relative=0)
        except Exception:
            pass
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

    file_paths_to_attach: set[str] = set()

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
        line_meta(meta, speaker_key=str(m.get('user_id') or m.get('user_label') or 'unknown'), gap=12, x=x)
        for l in wrap(m.get("text") or "", 116):
            line("  " + l, 9, 11, x=x)
        atts = m.get("attachments") or []
        if atts:
            line("  attachments:", 9, 11, x=x)
            for a in atts:
                link = attachment_link(a)
                name = a.get('name') or a.get('id') or 'attachment'
                line(f"    - {name} {link}", 8, 10, x=x)
                if link:
                    link_url = str(link)
                    if link_url.startswith('/'):
                        link_url = 'file://' + link_url
                    line_link(f"      open: {name}", link_url, 8, 10, x=x+10)
                lp = a.get("local_path")
                if lp:
                    file_paths_to_attach.add(str(lp))
                if args.embed_attachments and (a.get("mimetype") or "").lower().startswith("image/") and lp:
                    draw_image(str(lp), x=x + 10, max_width=252.0)
        line("", 9, 8, x=x)

    c.save()

    if args.attach_files and file_paths_to_attach:
        reader = PdfReader(str(out))
        writer = PdfWriter()
        for p in reader.pages:
            writer.add_page(p)
        attached = 0
        for fp in sorted(file_paths_to_attach):
            path = Path(fp)
            if not path.exists() or not path.is_file():
                continue
            try:
                writer.add_attachment(path.name, path.read_bytes())
                attached += 1
            except Exception:
                continue
        with out.open("wb") as f:
            writer.write(f)
        print(f"Attached files: {attached}")

    print(f"Wrote PDF: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
