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
THEME_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
FONT_TABLE_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable"
SETTINGS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings"
DEFAULT_BODY_FONT = "Arial"
DEFAULT_BODY_FONT_FALLBACK = "Liberation Sans"

ET.register_namespace("w", W_NS)
ET.register_namespace("r", R_NS)
ET.register_namespace("", PKG_REL_NS)


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def rel(tag: str) -> str:
    return f"{{{PKG_REL_NS}}}{tag}"


class ExportDocxStyle:
    def __init__(
        self,
        *,
        font_family: str = DEFAULT_BODY_FONT,
        font_family_fallback: str = DEFAULT_BODY_FONT_FALLBACK,
        body_font_size_pt: int = 10,
        margin_in: float = 1.0,
        compactness: str = "compact",
        accent_color: str = "3B5B7A",
        text_color: str = "1F2937",
        title_color: str = "0F172A",
        muted_color: str = "64748B",
        attachment_heading_color: str = "475569",
    ) -> None:
        self.font_family = font_family
        self.font_family_fallback = font_family_fallback
        self.body_font_size_pt = body_font_size_pt
        self.margin_in = margin_in
        self.compactness = compactness
        self.accent_color = accent_color
        self.text_color = text_color
        self.title_color = title_color
        self.muted_color = muted_color
        self.attachment_heading_color = attachment_heading_color

    def half_points(self, pt: int | float) -> str:
        return str(int(round(pt * 2)))

    def twips(self, inches: float) -> str:
        return str(int(round(inches * 1440)))

    @property
    def compact(self) -> bool:
        return self.compactness == "compact"


def _normalize_hex_color(value: str) -> str:
    cleaned = value.strip().lstrip("#").upper()
    if len(cleaned) != 6 or any(ch not in "0123456789ABCDEF" for ch in cleaned):
        raise ValueError(f"invalid hex color: {value}")
    return cleaned


def _build_style(
    *,
    font_family: str = DEFAULT_BODY_FONT,
    font_family_fallback: str = DEFAULT_BODY_FONT_FALLBACK,
    body_font_size_pt: int = 10,
    margin_in: float = 1.0,
    compactness: str = "compact",
    accent_color: str = "3B5B7A",
) -> ExportDocxStyle:
    if body_font_size_pt < 8 or body_font_size_pt > 16:
        raise ValueError("body_font_size_pt must be between 8 and 16")
    if margin_in < 0.5 or margin_in > 2.0:
        raise ValueError("margin_in must be between 0.5 and 2.0")
    if compactness not in {"compact", "cozy"}:
        raise ValueError("compactness must be 'compact' or 'cozy'")
    accent = _normalize_hex_color(accent_color)
    return ExportDocxStyle(
        font_family=font_family,
        font_family_fallback=font_family_fallback,
        body_font_size_pt=body_font_size_pt,
        margin_in=margin_in,
        compactness=compactness,
        accent_color=accent,
    )


def _serialize_xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _content_types_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/_rels/.rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/word/_rels/document.xml.rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
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


def _styles_xml(style: ExportDocxStyle) -> bytes:
    body_half = style.half_points(style.body_font_size_pt)
    title_half = style.half_points(style.body_font_size_pt + 4)
    heading_half = style.half_points(style.body_font_size_pt + 2)
    meta_half = style.half_points(max(style.body_font_size_pt - 1, 8))
    attachment_meta_half = style.half_points(max(style.body_font_size_pt - 2, 8))
    normal_after = "80" if style.compact else "120"
    title_after = "120" if style.compact else "180"
    heading_before = "80" if style.compact else "120"
    heading_after = "100" if style.compact else "140"
    meta_before = "60" if style.compact else "90"
    meta_after = "10" if style.compact else "20"
    reply_meta_before = "80" if style.compact else "120"
    body_after = "30" if style.compact else "60"
    attachment_heading_before = "24" if style.compact else "40"
    attachment_heading_after = "8" if style.compact else "16"
    attachment_item_after = "10" if style.compact else "20"
    attachment_meta_after = "8" if style.compact else "14"
    message_indent = "180" if style.compact else "240"
    reply_body_indent = "720" if style.compact else "900"
    attachment_heading_indent = "180" if style.compact else "240"
    attachment_item_indent = "420" if style.compact else "540"
    attachment_item_reply_indent = "1140" if style.compact else "1320"
    attachment_meta_indent = "600" if style.compact else "720"
    attachment_meta_reply_indent = "960" if style.compact else "1140"
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W_NS}">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:spacing w:line="240" w:lineRule="auto" w:after="{normal_after}"/></w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="{style.font_family}" w:hAnsi="{style.font_family}" w:cs="{style.font_family}"/>
      <w:color w:val="{style.text_color}"/>
      <w:sz w:val="{body_half}"/>
      <w:szCs w:val="{body_half}"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:spacing w:after="{title_after}"/></w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="{style.font_family}" w:hAnsi="{style.font_family}" w:cs="{style.font_family}"/>
      <w:b/>
      <w:color w:val="{style.title_color}"/>
      <w:sz w:val="{title_half}"/>
      <w:szCs w:val="{title_half}"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:spacing w:before="{heading_before}" w:after="{heading_after}"/></w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="{style.font_family}" w:hAnsi="{style.font_family}" w:cs="{style.font_family}"/>
      <w:b/>
      <w:color w:val="{style.title_color}"/>
      <w:sz w:val="{heading_half}"/>
      <w:szCs w:val="{heading_half}"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Meta">
    <w:name w:val="Meta"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="{meta_before}" w:after="{meta_after}"/></w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="{style.font_family}" w:hAnsi="{style.font_family}" w:cs="{style.font_family}"/>
      <w:sz w:val="{meta_half}"/>
      <w:szCs w:val="{meta_half}"/>
      <w:color w:val="{style.accent_color}"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="ReplyMeta">
    <w:name w:val="Reply Meta"/>
    <w:basedOn w:val="Meta"/>
    <w:pPr><w:ind w:left="720"/><w:spacing w:before="{reply_meta_before}" w:after="{meta_after}"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="MessageBody">
    <w:name w:val="Message Body"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:ind w:left="{message_indent}"/><w:spacing w:after="{body_after}"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="ReplyBody">
    <w:name w:val="Reply Body"/>
    <w:basedOn w:val="MessageBody"/>
    <w:pPr><w:ind w:left="{reply_body_indent}"/><w:spacing w:after="{body_after}"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="AttachmentHeading">
    <w:name w:val="Attachment Heading"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:ind w:left="{attachment_heading_indent}"/><w:spacing w:before="{attachment_heading_before}" w:after="{attachment_heading_after}"/></w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="{style.font_family}" w:hAnsi="{style.font_family}" w:cs="{style.font_family}"/>
      <w:b/>
      <w:color w:val="{style.attachment_heading_color}"/>
      <w:sz w:val="{meta_half}"/>
      <w:szCs w:val="{meta_half}"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="AttachmentItem">
    <w:name w:val="Attachment Item"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:ind w:left="{attachment_item_indent}"/><w:spacing w:after="{attachment_item_after}"/></w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="{style.font_family}" w:hAnsi="{style.font_family}" w:cs="{style.font_family}"/>
      <w:sz w:val="{meta_half}"/>
      <w:szCs w:val="{meta_half}"/>
      <w:color w:val="{style.accent_color}"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="AttachmentItemReply">
    <w:name w:val="Attachment Item Reply"/>
    <w:basedOn w:val="AttachmentItem"/>
    <w:pPr><w:ind w:left="{attachment_item_reply_indent}"/><w:spacing w:after="{attachment_item_after}"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="AttachmentMeta">
    <w:name w:val="Attachment Meta"/>
    <w:basedOn w:val="AttachmentItem"/>
    <w:pPr><w:ind w:left="{attachment_meta_indent}"/><w:spacing w:after="{attachment_meta_after}"/></w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="{style.font_family}" w:hAnsi="{style.font_family}" w:cs="{style.font_family}"/>
      <w:sz w:val="{attachment_meta_half}"/>
      <w:szCs w:val="{attachment_meta_half}"/>
      <w:color w:val="{style.muted_color}"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="AttachmentMetaReply">
    <w:name w:val="Attachment Meta Reply"/>
    <w:basedOn w:val="AttachmentMeta"/>
    <w:pPr><w:ind w:left="{attachment_meta_reply_indent}"/><w:spacing w:after="{attachment_meta_after}"/></w:pPr>
  </w:style>
</w:styles>
""".encode("utf-8")


def _font_table_xml(style: ExportDocxStyle) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:fonts xmlns:w="{W_NS}" xmlns:r="{R_NS}">
  <w:font w:name="{style.font_family}">
    <w:charset w:val="00"/>
    <w:family w:val="swiss"/>
    <w:pitch w:val="variable"/>
  </w:font>
  <w:font w:name="{style.font_family_fallback}">
    <w:altName w:val="{style.font_family}"/>
    <w:charset w:val="01"/>
    <w:family w:val="swiss"/>
    <w:pitch w:val="variable"/>
  </w:font>
</w:fonts>
""".encode("utf-8")


def _settings_xml() -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="{W_NS}">
  <w:zoom w:percent="100"/>
  <w:defaultTabStop w:val="720"/>
  <w:autoHyphenation w:val="false"/>
  <w:compat>
    <w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>
  </w:compat>
</w:settings>
""".encode("utf-8")


def _theme_xml(style: ExportDocxStyle) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="{R_NS}" name="SlackExport">
  <a:themeElements>
    <a:clrScheme name="SlackExport">
      <a:dk1><a:srgbClr val="{style.title_color}"/></a:dk1>
      <a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="{style.text_color}"/></a:dk2>
      <a:lt2><a:srgbClr val="F8FAFC"/></a:lt2>
      <a:accent1><a:srgbClr val="{style.accent_color}"/></a:accent1>
      <a:accent2><a:srgbClr val="{style.muted_color}"/></a:accent2>
      <a:accent3><a:srgbClr val="94A3B8"/></a:accent3>
      <a:accent4><a:srgbClr val="CBD5E1"/></a:accent4>
      <a:accent5><a:srgbClr val="0EA5E9"/></a:accent5>
      <a:accent6><a:srgbClr val="0F766E"/></a:accent6>
      <a:hlink><a:srgbClr val="{style.accent_color}"/></a:hlink>
      <a:folHlink><a:srgbClr val="{style.attachment_heading_color}"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="SlackExport">
      <a:majorFont>
        <a:latin typeface="{style.font_family}" pitchFamily="0" charset="1"/>
        <a:ea typeface="{style.font_family_fallback}" pitchFamily="0" charset="1"/>
        <a:cs typeface="{style.font_family_fallback}" pitchFamily="0" charset="1"/>
      </a:majorFont>
      <a:minorFont>
        <a:latin typeface="{style.font_family}" pitchFamily="0" charset="1"/>
        <a:ea typeface="{style.font_family_fallback}" pitchFamily="0" charset="1"/>
        <a:cs typeface="{style.font_family_fallback}" pitchFamily="0" charset="1"/>
      </a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="SlackExport">
      <a:fillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:fillStyleLst>
      <a:lnStyleLst>
        <a:ln w="6350" cap="flat" cmpd="sng" algn="ctr"><a:prstDash val="solid"/><a:miter/></a:ln>
        <a:ln w="6350" cap="flat" cmpd="sng" algn="ctr"><a:prstDash val="solid"/><a:miter/></a:ln>
        <a:ln w="6350" cap="flat" cmpd="sng" algn="ctr"><a:prstDash val="solid"/><a:miter/></a:ln>
      </a:lnStyleLst>
      <a:effectStyleLst>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
      </a:effectStyleLst>
      <a:bgFillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>
""".encode("utf-8")


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _attachment_type_label(mimetype: str) -> str:
    if not mimetype:
        return ""
    labels = {
        "application/pdf": "PDF document",
        "image/png": "PNG image",
        "image/jpeg": "JPEG image",
        "image/jpg": "JPEG image",
        "image/gif": "GIF image",
        "text/plain": "Plain text",
        "text/html": "HTML document",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PowerPoint presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel workbook",
        "application/vnd.oasis.opendocument.text": "OpenDocument text",
        "application/vnd.oasis.opendocument.presentation": "OpenDocument presentation",
        "application/vnd.oasis.opendocument.spreadsheet": "OpenDocument spreadsheet",
    }
    return labels.get(mimetype, mimetype)


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
    docx_style: ExportDocxStyle,
    style: str | None = None,
    indent_twips: int = 0,
) -> ET.Element:
    paragraph = _paragraph(style=style, indent_twips=indent_twips)
    hyperlink = ET.SubElement(paragraph, w("hyperlink"))
    hyperlink.set(f"{{{R_NS}}}id", rid)
    run = ET.SubElement(hyperlink, w("r"))
    rpr = ET.SubElement(run, w("rPr"))
    rfonts = ET.SubElement(rpr, w("rFonts"))
    rfonts.set(w("ascii"), docx_style.font_family)
    rfonts.set(w("hAnsi"), docx_style.font_family)
    rfonts.set(w("cs"), docx_style.font_family)
    color = ET.SubElement(rpr, w("color"))
    color.set(w("val"), docx_style.accent_color)
    size = ET.SubElement(rpr, w("sz"))
    size.set(w("val"), docx_style.half_points(max(docx_style.body_font_size_pt - 1, 8)))
    size_cs = ET.SubElement(rpr, w("szCs"))
    size_cs.set(w("val"), docx_style.half_points(max(docx_style.body_font_size_pt - 1, 8)))
    text_el = ET.SubElement(run, w("t"))
    text_el.text = label
    return paragraph


def _add_page_break(paragraph: ET.Element) -> None:
    run = ET.SubElement(paragraph, w("r"))
    br = ET.SubElement(run, w("br"))
    br.set(w("type"), "page")


def _append_export_block(
    body: ET.Element,
    data: dict,
    relationships: list[tuple[str, str]],
    next_rel_index: int,
    docx_style: ExportDocxStyle,
) -> int:
    title = f"{data.get('workspace')} / #{data.get('channel')}"
    body.append(_paragraph(title, style="Title", spacing_after=180))
    header_parts = [
        data.get("day") or "",
        data.get("tz") or "",
        data.get("channel_id") or "",
        f"{len(data.get('messages', []))} messages",
    ]
    body.append(_paragraph("  |  ".join(part for part in header_parts if part), style="Meta", spacing_after=140))

    for msg in data.get("messages", []):
        is_reply = bool(msg.get("thread_ts")) and str(msg.get("thread_ts")) != str(msg.get("ts"))
        indent = 540 if docx_style.compact else 720
        reply_indent = 720 if docx_style.compact else 900
        attachment_heading_indent = 180 if docx_style.compact else 240
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
            color=docx_style.accent_color,
        )
        _add_text_run(meta, msg.get("user_label") or msg.get("user_id") or "unknown", bold=True)
        if msg.get("deleted"):
            _add_text_run(meta, "  deleted", preserve_space=True)
        body.append(meta)

        body.append(
            _paragraph(
                msg.get("text") or "",
                style="ReplyBody" if is_reply else "MessageBody",
                indent_twips=reply_indent if is_reply else None,
            )
        )

        attachments = msg.get("attachments") or []
        if attachments:
            body.append(
                _paragraph(
                    "Attachments",
                    style="AttachmentHeading",
                    indent_twips=(reply_indent if is_reply else attachment_heading_indent),
                )
            )
            for att in attachments:
                name = att.get("name") or att.get("id") or "attachment"
                mimetype = att.get("mimetype") or ""
                local_path = att.get("local_path") or ""
                permalink = att.get("permalink") or ""
                link = local_path or permalink or ""
                label = name
                item_style = "AttachmentItemReply" if is_reply else "AttachmentItem"
                meta_style = "AttachmentMetaReply" if is_reply else "AttachmentMeta"
                if link:
                    rid = _next_rid(next_rel_index)
                    next_rel_index += 1
                    target = f"file://{link}" if str(link).startswith("/") else str(link)
                    relationships.append((rid, target))
                    body.append(_hyperlink_paragraph(label, target, rid, docx_style=docx_style, style=item_style))
                else:
                    body.append(_paragraph(label, style=item_style))
                if mimetype:
                    body.append(_paragraph(f"type: {_attachment_type_label(mimetype)}", style=meta_style))
                if local_path and permalink:
                    body.append(_paragraph(f"permalink: {permalink}", style=meta_style))
                elif local_path:
                    body.append(_paragraph("source: local file", style=meta_style))
                elif permalink:
                    body.append(_paragraph(f"permalink: {permalink}", style=meta_style))
    return next_rel_index


def _document_xml_for_exports(
    data_items: list[dict],
    relationships: list[tuple[str, str]],
    *,
    docx_style: ExportDocxStyle,
    package_title: str | None = None,
) -> bytes:
    document = ET.Element(w("document"))
    body = ET.SubElement(document, w("body"))
    next_rel_index = 1
    total = len(data_items)

    if package_title:
        body.append(_paragraph(package_title, style="Heading1", spacing_after=180))

    for index, data in enumerate(data_items):
        next_rel_index = _append_export_block(body, data, relationships, next_rel_index, docx_style)
        if index != total - 1:
            page_break = _paragraph()
            _add_page_break(page_break)
            body.append(page_break)

    sect_pr = ET.SubElement(body, w("sectPr"))
    pg_sz = ET.SubElement(sect_pr, w("pgSz"))
    pg_sz.set(w("w"), "12240")
    pg_sz.set(w("h"), "15840")
    pg_mar = ET.SubElement(sect_pr, w("pgMar"))
    for key, value in {
        "top": docx_style.twips(docx_style.margin_in),
        "right": docx_style.twips(docx_style.margin_in),
        "bottom": docx_style.twips(docx_style.margin_in),
        "left": docx_style.twips(docx_style.margin_in),
        "header": "720",
        "footer": "720",
        "gutter": "0",
    }.items():
        pg_mar.set(w(key), value)
    return _serialize_xml(document)


def _document_xml(data: dict, relationships: list[tuple[str, str]], *, docx_style: ExportDocxStyle) -> bytes:
    return _document_xml_for_exports([data], relationships, docx_style=docx_style)


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
    ET.SubElement(
        root,
        rel("Relationship"),
        {
            "Id": "rIdFontTable",
            "Type": FONT_TABLE_REL_TYPE,
            "Target": "fontTable.xml",
        },
    )
    ET.SubElement(
        root,
        rel("Relationship"),
        {
            "Id": "rIdSettings",
            "Type": SETTINGS_REL_TYPE,
            "Target": "settings.xml",
        },
    )
    ET.SubElement(
        root,
        rel("Relationship"),
        {
            "Id": "rIdTheme",
            "Type": THEME_REL_TYPE,
            "Target": "theme/theme1.xml",
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


def render_channel_day_docx(
    input_json: Path,
    output_docx: Path,
    *,
    docx_style: ExportDocxStyle | None = None,
) -> Path:
    docx_style = docx_style or _build_style()
    data = json.loads(input_json.read_text(encoding="utf-8"))
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    relationships: list[tuple[str, str]] = []
    title = f"{data.get('workspace')} #{data.get('channel')} {data.get('day')}"
    parts = {
        "[Content_Types].xml": _content_types_xml(),
        "_rels/.rels": _root_rels_xml(),
        "docProps/core.xml": _core_props_xml(title),
        "docProps/app.xml": _app_props_xml(),
        "word/styles.xml": _styles_xml(docx_style),
        "word/fontTable.xml": _font_table_xml(docx_style),
        "word/settings.xml": _settings_xml(),
        "word/theme/theme1.xml": _theme_xml(docx_style),
    }
    parts["word/document.xml"] = _document_xml(data, relationships, docx_style=docx_style)
    parts["word/_rels/document.xml.rels"] = _document_rels_xml(relationships)
    with zipfile.ZipFile(output_docx, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in parts.items():
            zf.writestr(name, payload)
    return output_docx


def render_multi_day_docx(
    json_paths: list[Path],
    output_docx: Path,
    *,
    package_title: str | None = None,
    docx_style: ExportDocxStyle | None = None,
) -> Path:
    docx_style = docx_style or _build_style()
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    data_items = [json.loads(path.read_text(encoding="utf-8")) for path in json_paths]
    relationships: list[tuple[str, str]] = []
    title = package_title or "Slack Export DOCX Package"
    parts = {
        "[Content_Types].xml": _content_types_xml(),
        "_rels/.rels": _root_rels_xml(),
        "docProps/core.xml": _core_props_xml(title),
        "docProps/app.xml": _app_props_xml(),
        "word/styles.xml": _styles_xml(docx_style),
        "word/fontTable.xml": _font_table_xml(docx_style),
        "word/settings.xml": _settings_xml(),
        "word/theme/theme1.xml": _theme_xml(docx_style),
    }
    parts["word/document.xml"] = _document_xml_for_exports(
        data_items,
        relationships,
        docx_style=docx_style,
        package_title=package_title,
    )
    parts["word/_rels/document.xml.rels"] = _document_rels_xml(relationships)
    with zipfile.ZipFile(output_docx, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in parts.items():
            zf.writestr(name, payload)
    return output_docx


def main() -> int:
    ap = argparse.ArgumentParser(description="Render exported channel-day JSON to DOCX")
    ap.add_argument("--input-json", required=True)
    ap.add_argument("--output-docx", required=True)
    ap.add_argument("--font-family", default=DEFAULT_BODY_FONT)
    ap.add_argument("--font-size-pt", type=int, default=10)
    ap.add_argument("--margin-in", type=float, default=1.0)
    ap.add_argument("--compactness", choices=("compact", "cozy"), default="compact")
    ap.add_argument("--accent-color", default="3B5B7A")
    args = ap.parse_args()
    docx_style = _build_style(
        font_family=args.font_family,
        body_font_size_pt=args.font_size_pt,
        margin_in=args.margin_in,
        compactness=args.compactness,
        accent_color=args.accent_color,
    )
    out = render_channel_day_docx(Path(args.input_json), Path(args.output_docx), docx_style=docx_style)
    print(f"Wrote DOCX: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
