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
    args = ap.parse_args()

    module = _load_export_docx_module()
    inputs = [Path(p) for p in args.inputs]
    out = Path(args.output_docx)
    module.render_multi_day_docx(inputs, out, package_title=args.title)
    print(f"Wrote combined DOCX: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
