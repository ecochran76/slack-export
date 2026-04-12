#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import posixpath
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


def _is_xml_part(path: str) -> bool:
    return path == "[Content_Types].xml" or path.endswith((".xml", ".rels"))


def _parse_xml_parts(zf: zipfile.ZipFile, names: set[str], issues: list[str]) -> dict[str, ET.Element]:
    parsed: dict[str, ET.Element] = {}
    for name in sorted(n for n in names if _is_xml_part(n)):
        try:
            parsed[name] = ET.fromstring(zf.read(name))
        except ET.ParseError as exc:
            issues.append(f"xml_parse_error:{name}:{exc}")
    return parsed


def _resolve_relationship_target(rels_path: str, target: str) -> str:
    base_dir = posixpath.dirname(rels_path)
    if base_dir.endswith("_rels"):
        source_dir = posixpath.dirname(base_dir)
    else:
        source_dir = base_dir
    return posixpath.normpath(posixpath.join(source_dir, target))


def _validate_content_type_overrides(
    content_types: ET.Element | None,
    names: set[str],
    issues: list[str],
) -> None:
    if content_types is None:
        return
    for override in content_types.findall(f".//{{{CONTENT_TYPES_NS}}}Override"):
        part_name = override.attrib.get("PartName", "")
        if not part_name.startswith("/"):
            issues.append(f"content_type_override_invalid:{part_name}")
            continue
        part_path = part_name.lstrip("/")
        if part_path not in names:
            issues.append(f"content_type_override_missing_part:{part_path}")


def _validate_relationship_targets(
    parsed_parts: dict[str, ET.Element],
    names: set[str],
    issues: list[str],
) -> None:
    for part_name, root in parsed_parts.items():
        if not part_name.endswith(".rels"):
            continue
        for rel in root.findall(f".//{{{PKG_REL_NS}}}Relationship"):
            target = rel.attrib.get("Target", "")
            if not target:
                issues.append(f"relationship_missing_target:{part_name}:{rel.attrib.get('Id', '')}")
                continue
            if rel.attrib.get("TargetMode") == "External":
                continue
            resolved = _resolve_relationship_target(part_name, target)
            if resolved not in names:
                issues.append(f"relationship_missing_target_part:{part_name}:{resolved}")


def inspect_docx(path: Path) -> dict:
    required_parts = {
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
        "word/_rels/document.xml.rels",
        "word/styles.xml",
    }
    issues: list[str] = []
    names: set[str] = set()
    parsed_parts: dict[str, ET.Element] = {}
    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        missing_parts = sorted(required_parts - names)
        if missing_parts:
            issues.extend(f"missing_part:{name}" for name in missing_parts)

        parsed_parts = _parse_xml_parts(zf, names, issues)

    content_types = parsed_parts.get("[Content_Types].xml")
    document = parsed_parts.get("word/document.xml")
    rels = parsed_parts.get("word/_rels/document.xml.rels")
    styles = parsed_parts.get("word/styles.xml")

    _validate_content_type_overrides(content_types, names, issues)
    _validate_relationship_targets(parsed_parts, names, issues)

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
