#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def inspect_docx(path: Path) -> dict:
    required_parts = {
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
        "word/_rels/document.xml.rels",
        "word/styles.xml",
    }
    issues: list[str] = []
    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        missing_parts = sorted(required_parts - names)
        if missing_parts:
            issues.extend(f"missing_part:{name}" for name in missing_parts)

        document = ET.fromstring(zf.read("word/document.xml")) if "word/document.xml" in names else None
        rels = ET.fromstring(zf.read("word/_rels/document.xml.rels")) if "word/_rels/document.xml.rels" in names else None
        styles = ET.fromstring(zf.read("word/styles.xml")) if "word/styles.xml" in names else None

    text_values = [elem.text or "" for elem in document.findall(f".//{{{W_NS}}}t")] if document is not None else []
    paragraph_styles = [
        elem.get(f"{{{W_NS}}}val")
        for elem in document.findall(f".//{{{W_NS}}}pPr/{{{W_NS}}}pStyle")
    ] if document is not None else []
    style_ids = sorted({
        elem.attrib.get(f"{{{W_NS}}}styleId")
        for elem in styles.findall(f".//{{{W_NS}}}style")
        if elem.attrib.get(f"{{{W_NS}}}styleId")
    }) if styles is not None else []
    page_breaks = [
        elem for elem in document.findall(f".//{{{W_NS}}}br")
        if elem.get(f"{{{W_NS}}}type") == "page"
    ] if document is not None else []
    hyperlinks = [
        {
            "id": rel.attrib.get("Id", ""),
            "target": rel.attrib.get("Target", ""),
            "target_mode": rel.attrib.get("TargetMode", ""),
        }
        for rel in rels.findall(f".//{{{PKG_REL_NS}}}Relationship")
        if rel.attrib.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
    ] if rels is not None else []

    style_requirements = {"Title", "Meta", "ReplyMeta", "MessageBody", "ReplyBody", "AttachmentItem"}
    missing_styles = sorted(style_requirements - set(style_ids))
    if missing_styles:
        issues.extend(f"missing_style:{style_id}" for style_id in missing_styles)

    if "[THREAD REPLY] " not in text_values:
        issues.append("missing_reply_badge_text")

    summary = {
        "path": str(path),
        "status": "ok" if not issues else "invalid",
        "issues": issues,
        "parts_present": sorted(names),
        "text_nodes": len(text_values),
        "page_break_count": len(page_breaks),
        "hyperlink_count": len(hyperlinks),
        "hyperlinks": hyperlinks,
        "style_ids": style_ids,
        "paragraph_style_usage": paragraph_styles,
        "contains_reply_badge": "[THREAD REPLY] " in text_values,
        "contains_local_source_note": "source: local file" in text_values,
        "contains_permalink_note": any((text or "").startswith("permalink: ") for text in text_values),
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a Slack export DOCX package")
    ap.add_argument("--input-docx", required=True)
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--fail-on-issues", action="store_true")
    args = ap.parse_args()

    summary = inspect_docx(Path(args.input_docx))
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"status: {summary['status']}")
        print(f"page_breaks: {summary['page_break_count']}")
        print(f"hyperlinks: {summary['hyperlink_count']}")
        print(f"styles: {', '.join(summary['style_ids'])}")
        if summary["issues"]:
            print("issues:")
            for issue in summary["issues"]:
                print(f"  - {issue}")
    if args.fail_on_issues and summary["issues"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
