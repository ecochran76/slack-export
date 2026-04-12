#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("w", W_NS)
ET.register_namespace("r", R_NS)


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def rel(tag: str) -> str:
    return f"{{{PKG_REL_NS}}}{tag}"


def _serialize_xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _content_types_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""


def _root_rels_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""


def _core_props_xml(title: str) -> bytes:
    safe_title = _xml_escape(title)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{safe_title}</dc:title>
  <dc:creator>slack-export</dc:creator>
  <cp:lastModifiedBy>slack-export</cp:lastModifiedBy>
</cp:coreProperties>
""".encode("utf-8")


def _app_props_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>slack-export</Application>
</Properties>
"""


def _styles_xml() -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W_NS}">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:spacing w:after="120"/></w:pPr>
    <w:rPr><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:spacing w:after="180"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:spacing w:before="120" w:after="120"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Meta">
    <w:name w:val="Meta"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="80" w:after="20"/></w:pPr>
    <w:rPr><w:sz w:val="20"/><w:color w:val="1F4E79"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="ReplyMeta">
    <w:name w:val="Reply Meta"/>
    <w:basedOn w:val="Meta"/>
    <w:pPr><w:ind w:left="720"/><w:spacing w:before="120" w:after="20"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="MessageBody">
    <w:name w:val="Message Body"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:ind w:left="240"/><w:spacing w:after="40"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="ReplyBody">
    <w:name w:val="Reply Body"/>
    <w:basedOn w:val="MessageBody"/>
    <w:pPr><w:ind w:left="960"/><w:spacing w:after="40"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="AttachmentHeading">
    <w:name w:val="Attachment Heading"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:ind w:left="240"/><w:spacing w:before="40" w:after="20"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="20"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="AttachmentItem">
    <w:name w:val="Attachment Item"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:ind w:left="480"/><w:spacing w:after="20"/></w:pPr>
    <w:rPr><w:sz w:val="20"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="AttachmentItemReply">
    <w:name w:val="Attachment Item Reply"/>
    <w:basedOn w:val="AttachmentItem"/>
    <w:pPr><w:ind w:left="1200"/><w:spacing w:after="20"/></w:pPr>
    <w:rPr><w:sz w:val="20"/></w:rPr>
  </w:style>
</w:styles>
""".encode("utf-8")


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _next_rid(existing: int) -> str:
    return f"rId{existing}"


def _add_text_run(
    paragraph: ET.Element,
    text: str,
    *,
    bold: bool = False,
    color: str | None = None,
    preserve_space: bool = False,
) -> None:
    run = ET.SubElement(paragraph, w("r"))
    if bold or color:
        rpr = ET.SubElement(run, w("rPr"))
        if bold:
            ET.SubElement(rpr, w("b"))
        if color:
            color_el = ET.SubElement(rpr, w("color"))
            color_el.set(w("val"), color)
    text_el = ET.SubElement(run, w("t"))
    text_el.text = text
    if preserve_space or text.startswith(" ") or text.endswith(" ") or "  " in text:
        text_el.set(f"{{{XML_NS}}}space", "preserve")


def _add_linebreak(paragraph: ET.Element) -> None:
    run = ET.SubElement(paragraph, w("r"))
    ET.SubElement(run, w("br"))


def _add_text_with_breaks(paragraph: ET.Element, text: str) -> None:
    lines = (text or "").splitlines()
    if not lines:
        _add_text_run(paragraph, "")
        return
    for index, line in enumerate(lines):
        if index:
            _add_linebreak(paragraph)
        _add_text_run(paragraph, line, preserve_space=True)


def _paragraph(
    text: str | None = None,
    *,
    style: str | None = None,
    indent_twips: int | None = None,
    spacing_before: int | None = None,
    spacing_after: int | None = None,
) -> ET.Element:
    paragraph = ET.Element(w("p"))
    if style or indent_twips is not None or spacing_before is not None or spacing_after is not None:
        ppr = ET.SubElement(paragraph, w("pPr"))
        if style:
            pstyle = ET.SubElement(ppr, w("pStyle"))
            pstyle.set(w("val"), style)
        if indent_twips is not None:
            ind = ET.SubElement(ppr, w("ind"))
            ind.set(w("left"), str(indent_twips))
        if spacing_before is not None or spacing_after is not None:
            spacing = ET.SubElement(ppr, w("spacing"))
            if spacing_before is not None:
                spacing.set(w("before"), str(spacing_before))
            if spacing_after is not None:
                spacing.set(w("after"), str(spacing_after))
    if text is not None:
        _add_text_with_breaks(paragraph, text)
    return paragraph


def _hyperlink_paragraph(
    label: str,
    url: str,
    rid: str,
    *,
    style: str | None = None,
    indent_twips: int = 0,
) -> ET.Element:
    paragraph = _paragraph(style=style, indent_twips=indent_twips)
    hyperlink = ET.SubElement(paragraph, w("hyperlink"))
    hyperlink.set(f"{{{R_NS}}}id", rid)
    run = ET.SubElement(hyperlink, w("r"))
    rpr = ET.SubElement(run, w("rPr"))
    color = ET.SubElement(rpr, w("color"))
    color.set(w("val"), "1155CC")
    ET.SubElement(rpr, w("u")).set(w("val"), "single")
    text_el = ET.SubElement(run, w("t"))
    text_el.text = label
    return paragraph


def _document_xml(data: dict, relationships: list[tuple[str, str]]) -> bytes:
    document = ET.Element(w("document"))
    body = ET.SubElement(document, w("body"))

    title = f"{data.get('workspace')} / #{data.get('channel')}"
    body.append(_paragraph(title, style="Title", spacing_after=180))
    body.append(_paragraph(f"Day: {data.get('day')} ({data.get('tz')})", spacing_after=80))
    body.append(_paragraph(f"Channel ID: {data.get('channel_id')}", spacing_after=80))
    body.append(_paragraph(f"Messages exported: {len(data.get('messages', []))}", spacing_after=200))

    next_rel_index = 1

    for msg in data.get("messages", []):
        is_reply = bool(msg.get("thread_ts")) and str(msg.get("thread_ts")) != str(msg.get("ts"))
        indent = 720 if is_reply else 0
        meta = _paragraph(
            style="ReplyMeta" if is_reply else "Meta",
            indent_twips=indent if not is_reply else None,
            spacing_before=120 if not is_reply else None,
            spacing_after=20 if not is_reply else None,
        )
        if is_reply:
            _add_text_run(meta, "[THREAD REPLY] ", bold=True, color="0F172A")
        _add_text_run(
            meta,
            f"[{msg.get('human_ts') or msg.get('ts')}] ",
            bold=True,
            color="1F4E79",
        )
        _add_text_run(meta, msg.get("user_label") or msg.get("user_id") or "unknown", bold=True)
        if msg.get("thread_ts"):
            _add_text_run(meta, f"  thread={msg.get('thread_ts')}", preserve_space=True)
        if msg.get("deleted"):
            _add_text_run(meta, "  deleted", preserve_space=True)
        body.append(meta)

        body.append(_paragraph(msg.get("text") or "", style="ReplyBody" if is_reply else "MessageBody"))

        attachments = msg.get("attachments") or []
        if attachments:
            body.append(_paragraph("Attachments", style="AttachmentHeading", indent_twips=indent + 240))
            for att in attachments:
                name = att.get("name") or att.get("id") or "attachment"
                mimetype = att.get("mimetype") or ""
                local_path = att.get("local_path") or ""
                permalink = att.get("permalink") or ""
                link = local_path or permalink or ""
                label = f"{name} ({mimetype})" if mimetype else name
                item_style = "AttachmentItemReply" if is_reply else "AttachmentItem"
                if link:
                    rid = _next_rid(next_rel_index)
                    next_rel_index += 1
                    target = f"file://{link}" if str(link).startswith("/") else str(link)
                    relationships.append((rid, target))
                    body.append(_hyperlink_paragraph(label, target, rid, style=item_style))
                else:
                    body.append(_paragraph(label, style=item_style))
                if local_path and permalink:
                    body.append(_paragraph(f"permalink: {permalink}", style=item_style))
                elif local_path:
                    body.append(_paragraph("source: local file", style=item_style))
                elif permalink:
                    body.append(_paragraph(f"permalink: {permalink}", style=item_style))

    sect_pr = ET.SubElement(body, w("sectPr"))
    pg_sz = ET.SubElement(sect_pr, w("pgSz"))
    pg_sz.set(w("w"), "12240")
    pg_sz.set(w("h"), "15840")
    pg_mar = ET.SubElement(sect_pr, w("pgMar"))
    for key, value in {
        "top": "1440",
        "right": "1440",
        "bottom": "1440",
        "left": "1440",
        "header": "720",
        "footer": "720",
        "gutter": "0",
    }.items():
        pg_mar.set(w(key), value)
    return _serialize_xml(document)


def _document_rels_xml(relationships: list[tuple[str, str]]) -> bytes:
    root = ET.Element(rel("Relationships"))
    ET.SubElement(
        root,
        rel("Relationship"),
        {
            "Id": "rIdStyles",
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
            "Target": "styles.xml",
        },
    )
    for rid, target in relationships:
        ET.SubElement(
            root,
            rel("Relationship"),
            {
                "Id": rid,
                "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                "Target": target,
                "TargetMode": "External",
            },
        )
    return _serialize_xml(root)


def render_channel_day_docx(input_json: Path, output_docx: Path) -> Path:
    data = json.loads(input_json.read_text(encoding="utf-8"))
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    relationships: list[tuple[str, str]] = []
    title = f"{data.get('workspace')} #{data.get('channel')} {data.get('day')}"
    parts = {
        "[Content_Types].xml": _content_types_xml(),
        "_rels/.rels": _root_rels_xml(),
        "docProps/core.xml": _core_props_xml(title),
        "docProps/app.xml": _app_props_xml(),
        "word/styles.xml": _styles_xml(),
    }
    parts["word/document.xml"] = _document_xml(data, relationships)
    parts["word/_rels/document.xml.rels"] = _document_rels_xml(relationships)
    with zipfile.ZipFile(output_docx, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in parts.items():
            zf.writestr(name, payload)
    return output_docx


def main() -> int:
    ap = argparse.ArgumentParser(description="Render exported channel-day JSON to DOCX")
    ap.add_argument("--input-json", required=True)
    ap.add_argument("--output-docx", required=True)
    args = ap.parse_args()
    out = render_channel_day_docx(Path(args.input_json), Path(args.output_docx))
    print(f"Wrote DOCX: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
