#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter


def wrap(text: str, width: int = 112) -> list[str]:
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


def render_json_exports(json_paths: list[Path], output_pdf: Path, embed_attachments: bool, attach_files: bool) -> None:
    c = canvas.Canvas(str(output_pdf), pagesize=letter)
    w, h = letter
    y = h - 40

    def line(s: str, size: int = 10, gap: int = 14, x: int = 40):
        nonlocal y
        if y < 50:
            c.showPage()
            y = h - 40
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", size)
        c.drawString(x, y, s[:185])
        y -= gap

    speaker_colors = [
        (0.0, 0.0, 0.0),
        (0.05, 0.18, 0.45),
        (0.0, 0.35, 0.1),
        (0.35, 0.12, 0.45),
        (0.45, 0.2, 0.0),
        (0.35, 0.0, 0.0),
    ]
    speaker_index: dict[str, int] = {}

    def line_meta(s: str, speaker_key: str, gap: int = 12, x: int = 40):
        nonlocal y
        if y < 50:
            c.showPage()
            y = h - 40
        idx = speaker_index.setdefault(speaker_key, len(speaker_index))
        r, g, b = speaker_colors[idx % len(speaker_colors)]
        c.setFillColorRGB(r, g, b)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, s[:185])
        c.setFillColorRGB(0, 0, 0)
        y -= gap

    def line_link(label: str, url: str, size: int = 9, gap: int = 12, x: int = 40):
        nonlocal y
        if y < 50:
            c.showPage()
            y = h - 40
        txt = ("🔗 " + label)[:185]
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
        nonlocal y
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

    line("Slack Export - Multi-day, multi-channel package", 14, 20)
    file_paths_to_attach: set[str] = set()

    for jp in json_paths:
        data = json.loads(jp.read_text(encoding="utf-8"))
        line("=" * 80, 9, 10)
        line(f"Workspace: {data.get('workspace')}   Channel: #{data.get('channel')} ({data.get('channel_id')})", 11, 14)
        line(f"Day: {data.get('day')} ({data.get('tz')})   Messages: {len(data.get('messages', []))}", 10, 16)

        for m in data.get("messages", []):
            is_reply = bool(m.get("thread_ts")) and str(m.get("thread_ts")) != str(m.get("ts"))
            x = 88 if is_reply else 40
            if is_reply:
                line("[THREAD REPLY]", 8, 10, x=x)
            line_meta(
                f"[{m.get('human_ts') or m.get('ts')}] {m.get('user_label') or m.get('user_id') or 'unknown'}",
                speaker_key=str(m.get('user_id') or m.get('user_label') or 'unknown'),
                gap=12,
                x=x,
            )
            for l in wrap(m.get("text") or "", 114):
                line("  " + l, 9, 11, x=x)
            atts = m.get("attachments") or []
            if atts:
                line("  attachments:", 9, 11, x=x)
                for a in atts:
                    link = a.get("local_path") or a.get("permalink") or ""
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
                    if embed_attachments and (a.get("mimetype") or "").lower().startswith("image/") and lp:
                        draw_image(str(lp), x=x + 10, max_width=252.0)
            line("", 9, 8, x=x)

    c.save()

    if attach_files and file_paths_to_attach:
        reader = PdfReader(str(output_pdf))
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
        with output_pdf.open("wb") as f:
            writer.write(f)
        print(f"Attached files: {attached}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Combine channel-day JSON exports into one PDF")
    ap.add_argument("--inputs", nargs="+", required=True, help="Input JSON export files")
    ap.add_argument("--output", required=True)
    ap.add_argument("--embed-attachments", action="store_true")
    ap.add_argument("--attach-files", action="store_true", help="attach source files to the output PDF")
    args = ap.parse_args()

    inputs = [Path(p) for p in args.inputs]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    render_json_exports(inputs, out, args.embed_attachments, args.attach_files)
    print(f"Wrote combined PDF: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
