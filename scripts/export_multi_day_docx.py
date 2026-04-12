#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def _load_export_docx_module():
    script_path = Path(__file__).resolve().parent / "export_channel_day_docx.py"
    spec = importlib.util.spec_from_file_location("export_channel_day_docx", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ap = argparse.ArgumentParser(description="Combine channel-day JSON exports into one DOCX")
    ap.add_argument("--inputs", nargs="+", required=True, help="Input JSON export files")
    ap.add_argument("--output-docx", required=True)
    ap.add_argument("--title", default="Slack Export DOCX Package")
    ap.add_argument("--font-family", default="Arial")
    ap.add_argument("--font-size-pt", type=int, default=10)
    ap.add_argument("--margin-in", type=float, default=1.0)
    ap.add_argument("--compactness", choices=("compact", "cozy"), default="compact")
    ap.add_argument("--accent-color", default="3B5B7A")
    args = ap.parse_args()

    module = _load_export_docx_module()
    inputs = [Path(p) for p in args.inputs]
    out = Path(args.output_docx)
    docx_style = module._build_style(
        font_family=args.font_family,
        body_font_size_pt=args.font_size_pt,
        margin_in=args.margin_in,
        compactness=args.compactness,
        accent_color=args.accent_color,
    )
    module.render_multi_day_docx(inputs, out, package_title=args.title, docx_style=docx_style)
    print(f"Wrote combined DOCX: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
