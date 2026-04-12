from __future__ import annotations

import html
import json
import re
import shlex
import shutil
import subprocess
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from typing import Protocol
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from xml.etree import ElementTree as ET

from slack_mirror.core.db import (
    get_derived_text,
    list_pending_derived_text_jobs,
    mark_derived_text_job_status,
    upsert_derived_text,
)

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_SAFE_TEXT_SUFFIXES = {
    ".csv",
    ".htm",
    ".html",
    ".json",
    ".log",
    ".md",
    ".rst",
    ".text",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_SAFE_TEXT_MEDIA_TYPES = {
    "application/json",
    "application/ld+json",
    "application/xml",
    "text/csv",
    "text/html",
    "text/markdown",
    "text/plain",
    "text/tab-separated-values",
    "text/xml",
}
_OOXML_SUFFIXES = {
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "ooxml_docx"),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "ooxml_pptx"),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "ooxml_xlsx"),
}
_OPENDOCUMENT_SUFFIXES = {
    ".odt": ("application/vnd.oasis.opendocument.text", "odf_odt"),
    ".odp": ("application/vnd.oasis.opendocument.presentation", "odf_odp"),
    ".ods": ("application/vnd.oasis.opendocument.spreadsheet", "odf_ods"),
}
_OCR_IMAGE_SUFFIXES = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W_TAG_PREFIX = f"{{{_W_NS}}}"
_DOCX_STORY_PARTS = (
    "word/document.xml",
    "word/footnotes.xml",
    "word/endnotes.xml",
)
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_A_TAG_PREFIX = f"{{{_A_NS}}}"
_SS_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_SS_TAG_PREFIX = f"{{{_SS_NS}}}"


ExtractResult = tuple[str | None, dict]


def _provider_name(provider: object) -> str:
    return str(getattr(provider, "name", provider.__class__.__name__))


def _config_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"", "default"}:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


class DerivedTextProvider(Protocol):
    name: str

    def extract_attachment_text(self, conn, *, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
        ...

    def extract_ocr_text(self, conn, *, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
        ...


def _normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", (value or "").strip()).strip()


def _html_to_text(raw_html: str) -> str:
    cleaned = _SCRIPT_STYLE_RE.sub(" ", raw_html or "")
    cleaned = _TAG_RE.sub(" ", cleaned)
    return _normalize_text(html.unescape(cleaned))


def _extract_utf8_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() in {".htm", ".html"}:
        return _html_to_text(raw)
    return _normalize_text(raw)


def _extract_xml_text(raw_xml: bytes) -> str:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        return ""
    parts: list[str] = []
    for value in root.itertext():
        normalized = _normalize_text(value)
        if normalized:
            parts.append(normalized)
    return _normalize_text(" ".join(parts))


def _word_tag(local_name: str) -> str:
    return f"{_W_TAG_PREFIX}{local_name}"


def _extract_wordprocessingml_visible_text(raw_xml: bytes) -> str:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        return ""

    parts: list[str] = []
    for child in root.iter():
        if child.tag in {_word_tag("t"), _word_tag("delText")}:
            if child.text:
                parts.append(child.text)
        elif child.tag == _word_tag("tab"):
            parts.append("	")
        elif child.tag in {_word_tag("br"), _word_tag("cr")}:
            parts.append("\n")
    return _normalize_text("".join(parts))


def _drawingml_tag(local_name: str) -> str:
    return f"{_A_TAG_PREFIX}{local_name}"


def _spreadsheet_tag(local_name: str) -> str:
    return f"{_SS_TAG_PREFIX}{local_name}"


def _extract_pptx_slide_text(raw_xml: bytes) -> str:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        return ""
    parts: list[str] = []
    for child in root.iter():
        if child.tag == _drawingml_tag("t") and child.text:
            parts.append(child.text)
        elif child.tag == _drawingml_tag("tab"):
            parts.append("\t")
        elif child.tag == _drawingml_tag("br"):
            parts.append("\n")
    return _normalize_text("".join(parts))


def _extract_pptx_text(path: Path) -> tuple[str | None, str | None]:
    extractor = "ooxml_pptx"
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            parts: list[str] = []
            for member in sorted(name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")):
                extracted = _extract_pptx_slide_text(zf.read(member))
                if extracted:
                    parts.append(extracted)
            merged = _normalize_text(" ".join(parts))
            return (merged or None), extractor
    except (OSError, zipfile.BadZipFile):
        return None, extractor


def _extract_pptx_slides(path: Path) -> list[dict[str, Any]]:
    slides: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            for index, member in enumerate(
                sorted(name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")),
                start=1,
            ):
                extracted = _extract_pptx_slide_text(zf.read(member))
                if extracted:
                    slides.append(
                        {
                            "index": index,
                            "title": f"Slide {index}",
                            "text": extracted,
                        }
                    )
    except (OSError, zipfile.BadZipFile):
        return []
    return slides


def _extract_xlsx_shared_strings(raw_xml: bytes) -> list[str]:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        return []
    values: list[str] = []
    for si in root.findall(f".//{_spreadsheet_tag('si')}"):
        parts: list[str] = []
        for node in si.iter():
            if node.tag == _spreadsheet_tag("t") and node.text:
                parts.append(node.text)
        values.append(_normalize_text("".join(parts)))
    return values


def _extract_xlsx_sheet_text(raw_xml: bytes, shared_strings: list[str]) -> str:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        return ""
    parts: list[str] = []
    for cell in root.findall(f".//{_spreadsheet_tag('c')}"):
        cell_type = cell.get("t") or cell.get(_spreadsheet_tag("t")) or ""
        if cell_type == "s":
            value_node = cell.find(_spreadsheet_tag("v"))
            if value_node is None or not value_node.text:
                continue
            try:
                idx = int(value_node.text.strip())
            except ValueError:
                continue
            if 0 <= idx < len(shared_strings):
                value = shared_strings[idx]
                if value:
                    parts.append(value)
        elif cell_type == "inlineStr":
            inline = cell.find(f".//{_spreadsheet_tag('is')}")
            if inline is None:
                continue
            inline_parts = [node.text for node in inline.iter() if node.tag == _spreadsheet_tag("t") and node.text]
            value = _normalize_text("".join(inline_parts))
            if value:
                parts.append(value)
        else:
            value_node = cell.find(_spreadsheet_tag("v"))
            if value_node is not None and value_node.text:
                value = _normalize_text(value_node.text)
                if value:
                    parts.append(value)
    return _normalize_text(" ".join(parts))


def _extract_xlsx_sheet_rows(raw_xml: bytes, shared_strings: list[str]) -> list[list[str]]:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        return []
    rows: list[list[str]] = []
    for row in root.findall(f".//{_spreadsheet_tag('row')}"):
        values: list[str] = []
        for cell in row.findall(_spreadsheet_tag("c")):
            cell_type = cell.get("t") or cell.get(_spreadsheet_tag("t")) or ""
            value = ""
            if cell_type == "s":
                value_node = cell.find(_spreadsheet_tag("v"))
                if value_node is not None and value_node.text:
                    try:
                        idx = int(value_node.text.strip())
                    except ValueError:
                        idx = -1
                    if 0 <= idx < len(shared_strings):
                        value = shared_strings[idx]
            elif cell_type == "inlineStr":
                inline = cell.find(f".//{_spreadsheet_tag('is')}")
                if inline is not None:
                    inline_parts = [node.text for node in inline.iter() if node.tag == _spreadsheet_tag("t") and node.text]
                    value = _normalize_text("".join(inline_parts))
            else:
                value_node = cell.find(_spreadsheet_tag("v"))
                if value_node is not None and value_node.text:
                    value = _normalize_text(value_node.text)
            values.append(value)
        if any(v for v in values):
            rows.append(values)
    return rows


def _extract_xlsx_text(path: Path) -> tuple[str | None, str | None]:
    extractor = "ooxml_xlsx"
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            shared_strings = _extract_xlsx_shared_strings(zf.read("xl/sharedStrings.xml")) if "xl/sharedStrings.xml" in names else []
            parts: list[str] = []
            for member in sorted(name for name in names if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")):
                extracted = _extract_xlsx_sheet_text(zf.read(member), shared_strings)
                if extracted:
                    parts.append(extracted)
            merged = _normalize_text(" ".join(parts))
            return (merged or None), extractor
    except (OSError, zipfile.BadZipFile):
        return None, extractor


def _extract_xlsx_sheets(path: Path) -> list[dict[str, Any]]:
    sheets: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            shared_strings = _extract_xlsx_shared_strings(zf.read("xl/sharedStrings.xml")) if "xl/sharedStrings.xml" in names else []
            for index, member in enumerate(
                sorted(name for name in names if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")),
                start=1,
            ):
                rows = _extract_xlsx_sheet_rows(zf.read(member), shared_strings)
                if rows:
                    sheets.append(
                        {
                            "index": index,
                            "title": f"Sheet {index}",
                            "rows": rows,
                        }
                    )
    except (OSError, zipfile.BadZipFile):
        return []
    return sheets


def _extract_docx_text(path: Path) -> tuple[str | None, str | None]:
    extractor = "ooxml_docx"
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            parts: list[str] = []
            for member in _DOCX_STORY_PARTS:
                if member in names:
                    extracted = _extract_wordprocessingml_visible_text(zf.read(member))
                    if extracted:
                        parts.append(extracted)
            for member in sorted(name for name in names if name.startswith("word/header") and name.endswith(".xml")):
                extracted = _extract_wordprocessingml_visible_text(zf.read(member))
                if extracted:
                    parts.append(extracted)
            for member in sorted(name for name in names if name.startswith("word/footer") and name.endswith(".xml")):
                extracted = _extract_wordprocessingml_visible_text(zf.read(member))
                if extracted:
                    parts.append(extracted)
            merged = _normalize_text(" ".join(parts))
            return (merged or None), extractor
    except (OSError, zipfile.BadZipFile):
        return None, extractor


def _extract_ooxml_text(path: Path) -> tuple[str | None, str | None]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _extract_docx_text(path)
    if suffix == ".pptx":
        return _extract_pptx_text(path)
    if suffix == ".xlsx":
        return _extract_xlsx_text(path)
    return None, None


def render_ooxml_preview_html(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".pptx":
        slides = _extract_pptx_slides(path)
        if not slides:
            return None
        sections = []
        for slide in slides:
            lines = "<br>".join(html.escape(part) for part in str(slide["text"]).splitlines() if part.strip())
            sections.append(
                "<section style=\"border:1px solid #d1d5db;border-radius:8px;padding:16px;background:#fff;margin-bottom:16px\">"
                f"<h2 style=\"margin:0 0 12px;font-size:18px\">{html.escape(str(slide['title']))}</h2>"
                f"<div style=\"line-height:1.5\">{lines}</div>"
                "</section>"
            )
        return (
            "<article>"
            "<header style=\"margin-bottom:16px\"><strong>PowerPoint preview</strong></header>"
            f"{''.join(sections)}"
            "</article>"
        )
    if suffix == ".xlsx":
        sheets = _extract_xlsx_sheets(path)
        if not sheets:
            return None
        sections = []
        for sheet in sheets:
            rows = []
            for row in sheet["rows"][:25]:
                cells = "".join(
                    f"<td style=\"border:1px solid #d1d5db;padding:6px 8px;vertical-align:top\">{html.escape(value or '')}</td>"
                    for value in row
                )
                rows.append(f"<tr>{cells}</tr>")
            sections.append(
                "<section style=\"margin-bottom:20px\">"
                f"<h2 style=\"margin:0 0 10px;font-size:18px\">{html.escape(str(sheet['title']))}</h2>"
                "<div style=\"overflow:auto\">"
                "<table style=\"border-collapse:collapse;min-width:320px;background:#fff\">"
                f"{''.join(rows)}"
                "</table></div></section>"
            )
        return (
            "<article>"
            "<header style=\"margin-bottom:16px\"><strong>Spreadsheet preview</strong></header>"
            f"{''.join(sections)}"
            "</article>"
        )
    return None


def _extract_opendocument_text(path: Path) -> tuple[str | None, str | None]:
    suffix = path.suffix.lower()
    meta = _OPENDOCUMENT_SUFFIXES.get(suffix)
    if not meta:
        return None, None
    _, extractor = meta

    try:
        with zipfile.ZipFile(path) as zf:
            if "content.xml" not in set(zf.namelist()):
                return None, extractor
            extracted = _extract_xml_text(zf.read("content.xml"))
            return (extracted or None), extractor
    except (OSError, zipfile.BadZipFile):
        return None, extractor


def _extract_pdf_text(path: Path) -> str | None:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return None
    result = subprocess.run(
        [pdftotext, str(path), "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    text = _normalize_text(result.stdout)
    return text or None


def _run_text_command(args: list[str]) -> str | None:
    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    text = _normalize_text(result.stdout)
    return text or None


def _extract_image_ocr_text(path: Path) -> str | None:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return None
    return _run_text_command([tesseract, str(path), "stdout"])


def _extract_pdf_ocr_text(path: Path) -> tuple[str | None, dict]:
    if _extract_pdf_text(path):
        return None, {"error": "pdf_has_text_layer"}

    pdftoppm = shutil.which("pdftoppm")
    tesseract = shutil.which("tesseract")
    if not pdftoppm or not tesseract:
        return None, {"error": "ocr_tools_unavailable"}

    with tempfile.TemporaryDirectory(prefix="slack-mirror-ocr-") as td:
        prefix = str(Path(td) / "page")
        render = subprocess.run(
            [pdftoppm, "-png", str(path), prefix],
            check=False,
            capture_output=True,
            text=True,
        )
        if render.returncode != 0:
            return None, {"error": "pdf_render_failed"}

        page_images = sorted(Path(td).glob("page-*.png"))
        if not page_images:
            return None, {"error": "pdf_render_no_pages"}

        parts: list[str] = []
        for page_image in page_images:
            text = _extract_image_ocr_text(page_image)
            if text:
                parts.append(text)
        merged = _normalize_text(" ".join(parts))
        if not merged:
            return None, {"error": "ocr_no_text_detected"}
        return merged, {"pages": len(page_images)}


def _resolve_source_row(conn, *, workspace_id: int, source_kind: str, source_id: str):
    if source_kind == "file":
        return conn.execute(
            """
            SELECT file_id AS source_id, name, title, mimetype, local_path
            FROM files
            WHERE workspace_id = ? AND file_id = ?
            """,
            (workspace_id, source_id),
        ).fetchone()
    if source_kind == "canvas":
        return conn.execute(
            """
            SELECT canvas_id AS source_id, title, local_path
            FROM canvases
            WHERE workspace_id = ? AND canvas_id = ?
            """,
            (workspace_id, source_id),
        ).fetchone()
    raise ValueError(f"Unsupported source kind: {source_kind}")


def _extract_attachment_text_local(conn, *, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
    row = _resolve_source_row(conn, workspace_id=workspace_id, source_kind=source_kind, source_id=source_id)
    if not row:
        return None, {"error": "source_missing"}

    local_path = row["local_path"]
    if not local_path:
        return None, {"error": "local_path_missing"}

    path = Path(str(local_path)).expanduser()
    if not path.exists():
        return None, {"error": "local_path_missing"}

    if source_kind == "canvas":
        text = _extract_utf8_text(path)
        return (text or None), {
            "extractor": "canvas_html",
            "local_path": str(path),
            "media_type": "text/html",
        }

    media_type = str(row["mimetype"] or "")
    suffix = path.suffix.lower()
    if suffix == ".pdf" or media_type == "application/pdf":
        text = _extract_pdf_text(path)
        if text:
            return text, {
                "extractor": "pdftotext",
                "local_path": str(path),
                "media_type": media_type or "application/pdf",
            }
        return None, {
            "error": "pdf_text_unavailable",
            "local_path": str(path),
            "media_type": media_type or "application/pdf",
        }

    if suffix in _OOXML_SUFFIXES or media_type in {meta[0] for meta in _OOXML_SUFFIXES.values()}:
        text, extractor = _extract_ooxml_text(path)
        if text and extractor:
            return text, {
                "extractor": extractor,
                "local_path": str(path),
                "media_type": media_type or _OOXML_SUFFIXES.get(suffix, (None,))[0],
            }
        return None, {
            "error": "ooxml_text_unavailable",
            "local_path": str(path),
            "media_type": media_type or _OOXML_SUFFIXES.get(suffix, (None,))[0],
        }

    if suffix in _OPENDOCUMENT_SUFFIXES or media_type in {meta[0] for meta in _OPENDOCUMENT_SUFFIXES.values()}:
        text, extractor = _extract_opendocument_text(path)
        if text and extractor:
            return text, {
                "extractor": extractor,
                "local_path": str(path),
                "media_type": media_type or _OPENDOCUMENT_SUFFIXES.get(suffix, (None,))[0],
            }
        return None, {
            "error": "opendocument_text_unavailable",
            "local_path": str(path),
            "media_type": media_type or _OPENDOCUMENT_SUFFIXES.get(suffix, (None,))[0],
        }

    if suffix in _SAFE_TEXT_SUFFIXES or media_type in _SAFE_TEXT_MEDIA_TYPES or media_type.startswith("text/"):
        text = _extract_utf8_text(path)
        if text:
            return text, {
                "extractor": "utf8_text",
                "local_path": str(path),
                "media_type": media_type or None,
            }
        return None, {
            "error": "no_text_detected",
            "local_path": str(path),
            "media_type": media_type or None,
        }

    return None, {
        "error": "unsupported_media_type",
        "local_path": str(path),
        "media_type": media_type or None,
    }


def _extract_ocr_text_local(conn, *, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
    row = _resolve_source_row(conn, workspace_id=workspace_id, source_kind=source_kind, source_id=source_id)
    if not row:
        return None, {"error": "source_missing"}
    if source_kind != "file":
        return None, {"error": "unsupported_source_kind"}

    local_path = row["local_path"]
    if not local_path:
        return None, {"error": "local_path_missing"}

    path = Path(str(local_path)).expanduser()
    if not path.exists():
        return None, {"error": "local_path_missing"}

    media_type = str(row["mimetype"] or "")
    suffix = path.suffix.lower()
    if media_type == "application/pdf" or suffix == ".pdf":
        text, details = _extract_pdf_ocr_text(path)
        return text, {
            "extractor": "tesseract_pdf",
            "local_path": str(path),
            "media_type": media_type or "application/pdf",
            **details,
        }

    if media_type.startswith("image/") or suffix in _OCR_IMAGE_SUFFIXES:
        text = _extract_image_ocr_text(path)
        if text:
            return text, {
                "extractor": "tesseract_image",
                "local_path": str(path),
                "media_type": media_type or None,
            }
        missing_tools = not shutil.which("tesseract")
        return None, {
            "error": "ocr_tools_unavailable" if missing_tools else "ocr_no_text_detected",
            "local_path": str(path),
            "media_type": media_type or None,
        }

    return None, {
        "error": "unsupported_media_type",
        "local_path": str(path),
        "media_type": media_type or None,
    }


class LocalCliDerivedTextProvider:
    name = "local_host_tools"

    def extract_attachment_text(self, conn, *, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
        return _extract_attachment_text_local(
            conn,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
        )

    def extract_ocr_text(self, conn, *, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
        return _extract_ocr_text_local(
            conn,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
        )


class CommandDerivedTextProvider:
    def __init__(self, command: list[str]):
        if not command:
            raise ValueError("command provider requires a non-empty command")
        self.command = [str(part) for part in command]
        self.name = f"command:{Path(self.command[0]).name}"

    def _source_request(self, conn, *, workspace_id: int, source_kind: str, source_id: str) -> dict[str, Any]:
        row = _resolve_source_row(conn, workspace_id=workspace_id, source_kind=source_kind, source_id=source_id)
        if not row:
            return {"error": "source_missing"}
        local_path = row["local_path"]
        if not local_path:
            return {"error": "local_path_missing"}
        path = Path(str(local_path)).expanduser()
        if not path.exists():
            return {"error": "local_path_missing"}
        return {
            "source_kind": source_kind,
            "source_id": source_id,
            "local_path": str(path),
            "media_type": str(row["mimetype"] or "") if "mimetype" in row.keys() else None,
            "title": str(row["title"] or "") if "title" in row.keys() else None,
            "name": str(row["name"] or "") if "name" in row.keys() else None,
        }

    def _invoke(self, *, action: str, conn, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
        request = self._source_request(
            conn,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
        )
        if request.get("error"):
            return None, {"error": str(request["error"])}
        payload = {
            "action": action,
            "workspace_id": int(workspace_id),
            **request,
        }
        result = subprocess.run(
            self.command,
            check=False,
            capture_output=True,
            text=True,
            input=json.dumps(payload),
        )
        if result.returncode != 0:
            return None, {"error": "provider_command_failed", "stderr": _normalize_text(result.stderr)}
        try:
            response = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return None, {"error": "provider_invalid_json"}
        if not response.get("ok", True):
            return None, {"error": str(response.get("error") or "provider_error")}
        response_text = _normalize_text(str(response.get("text") or ""))
        if not response_text:
            return None, {"error": str(response.get("error") or "no_text_detected")}
        details = dict(response.get("details") or {})
        details.setdefault("extractor", str(response.get("extractor") or self.name))
        details.setdefault("media_type", request.get("media_type"))
        details.setdefault("local_path", request.get("local_path"))
        return response_text, details

    def extract_attachment_text(self, conn, *, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
        return self._invoke(
            action="attachment_text",
            conn=conn,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
        )

    def extract_ocr_text(self, conn, *, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
        return self._invoke(
            action="ocr_text",
            conn=conn,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
        )


class HttpDerivedTextProvider:
    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        bearer_token_env: str | None = None,
        timeout_s: float = 120.0,
    ):
        normalized_url = str(url or '').strip()
        if not normalized_url:
            raise ValueError('http provider requires a non-empty url')
        parsed = urllib_parse.urlparse(normalized_url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise ValueError('http provider requires an absolute http(s) url')
        self.url = normalized_url
        self.headers = {str(k): str(v) for k, v in (headers or {}).items()}
        self.bearer_token_env = None if bearer_token_env is None else (str(bearer_token_env).strip() or None)
        self.timeout_s = float(timeout_s)
        self.name = f"http:{parsed.netloc}"

    def _source_request(self, conn, *, workspace_id: int, source_kind: str, source_id: str) -> dict[str, Any]:
        row = _resolve_source_row(conn, workspace_id=workspace_id, source_kind=source_kind, source_id=source_id)
        if not row:
            return {'error': 'source_missing'}
        local_path = row['local_path']
        if not local_path:
            return {'error': 'local_path_missing'}
        path = Path(str(local_path)).expanduser()
        if not path.exists():
            return {'error': 'local_path_missing'}
        return {
            'source_kind': source_kind,
            'source_id': source_id,
            'local_path': str(path),
            'media_type': str(row['mimetype'] or '') if 'mimetype' in row.keys() else None,
            'title': str(row['title'] or '') if 'title' in row.keys() else None,
            'name': str(row['name'] or '') if 'name' in row.keys() else None,
        }

    def _invoke(self, *, action: str, conn, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
        request = self._source_request(
            conn,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
        )
        if request.get('error'):
            return None, {'error': str(request['error'])}
        payload = {
            'action': action,
            'workspace_id': int(workspace_id),
            **request,
        }
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json', **self.headers}
        if self.bearer_token_env:
            token = os.environ.get(self.bearer_token_env, '').strip()
            if not token:
                return None, {'error': 'provider_auth_missing'}
            headers.setdefault('Authorization', f'Bearer {token}')
        req = urllib_request.Request(
            self.url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST',
        )
        try:
            with urllib_request.urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode('utf-8', errors='replace')
        except urllib_error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            return None, {'error': 'provider_http_error', 'status_code': exc.code, 'response': _normalize_text(body)}
        except urllib_error.URLError as exc:
            return None, {'error': 'provider_connection_failed', 'reason': _normalize_text(str(exc.reason))}
        try:
            response = json.loads(body or '{}')
        except json.JSONDecodeError:
            return None, {'error': 'provider_invalid_json'}
        if not response.get('ok', True):
            return None, {'error': str(response.get('error') or 'provider_error')}
        response_text = _normalize_text(str(response.get('text') or ''))
        if not response_text:
            return None, {'error': str(response.get('error') or 'no_text_detected')}
        details = dict(response.get('details') or {})
        details.setdefault('extractor', str(response.get('extractor') or self.name))
        details.setdefault('media_type', request.get('media_type'))
        details.setdefault('local_path', request.get('local_path'))
        return response_text, details

    def extract_attachment_text(self, conn, *, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
        return self._invoke(
            action='attachment_text',
            conn=conn,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
        )

    def extract_ocr_text(self, conn, *, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
        return self._invoke(
            action='ocr_text',
            conn=conn,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
        )


class FallbackDerivedTextProvider:
    def __init__(self, primary: DerivedTextProvider, fallback: DerivedTextProvider):
        self.primary = primary
        self.fallback = fallback
        self.name = f"fallback:{_provider_name(primary)}->{_provider_name(fallback)}"

    def _with_provider(self, details: dict[str, Any] | None, provider: DerivedTextProvider, **extra: Any) -> dict[str, Any]:
        merged = dict(details or {})
        merged.setdefault("provider_name", _provider_name(provider))
        for key, value in extra.items():
            if value is not None:
                merged.setdefault(key, value)
        return merged

    def _invoke(self, method_name: str, conn, *, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
        method = getattr(self.primary, method_name)
        text, details = method(
            conn,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
        )
        if text:
            return text, self._with_provider(details, self.primary)

        fallback_method = getattr(self.fallback, method_name)
        fallback_text, fallback_details = fallback_method(
            conn,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
        )
        if fallback_text:
            return fallback_text, self._with_provider(
                fallback_details,
                self.fallback,
                fallback_from=_provider_name(self.primary),
                fallback_error=str((details or {}).get("error") or "provider_no_text"),
            )

        primary_details = self._with_provider(details, self.primary)
        fallback_details = self._with_provider(fallback_details, self.fallback)
        primary_details.setdefault("fallback_attempted", True)
        primary_details.setdefault("fallback_provider", fallback_details.get("provider_name"))
        primary_details.setdefault("fallback_error", str(fallback_details.get("error") or "fallback_no_text"))
        return None, primary_details

    def extract_attachment_text(self, conn, *, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
        return self._invoke(
            "extract_attachment_text",
            conn,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
        )

    def extract_ocr_text(self, conn, *, workspace_id: int, source_kind: str, source_id: str) -> ExtractResult:
        return self._invoke(
            "extract_ocr_text",
            conn,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
        )


_DEFAULT_PROVIDER = LocalCliDerivedTextProvider()


def build_derived_text_provider(config: dict[str, Any] | None = None) -> DerivedTextProvider:
    search = dict((config or {}).get("search") or {})
    derived_cfg = dict(search.get("derived_text") or {})
    provider_cfg = dict(derived_cfg.get("provider") or {})
    provider_type = str(provider_cfg.get("type") or "local_host_tools").strip().lower()
    if provider_type in {"", "local", "local_host_tools"}:
        return _DEFAULT_PROVIDER
    if provider_type == "command":
        command_value = provider_cfg.get("command")
        if isinstance(command_value, str):
            command = shlex.split(command_value)
        elif isinstance(command_value, list):
            command = [str(part) for part in command_value]
        else:
            command = []
        provider: DerivedTextProvider = CommandDerivedTextProvider(command)
        if _config_bool(provider_cfg.get("fallback_to_local"), default=True):
            provider = FallbackDerivedTextProvider(provider, _DEFAULT_PROVIDER)
        return provider
    if provider_type == "http":
        headers_value = provider_cfg.get("headers")
        headers = headers_value if isinstance(headers_value, dict) else {}
        provider = HttpDerivedTextProvider(
            str(provider_cfg.get("url") or ""),
            headers=headers,
            bearer_token_env=provider_cfg.get("bearer_token_env"),
            timeout_s=float(provider_cfg.get("timeout_s") or 120.0),
        )
        if _config_bool(provider_cfg.get("fallback_to_local"), default=True):
            provider = FallbackDerivedTextProvider(provider, _DEFAULT_PROVIDER)
        return provider
    raise ValueError(f"Unsupported derived-text provider type: {provider_type}")


def get_default_derived_text_provider() -> DerivedTextProvider:
    return _DEFAULT_PROVIDER


def process_derived_text_jobs(
    conn,
    *,
    workspace_id: int,
    derivation_kind: str = "attachment_text",
    limit: int = 100,
    provider: DerivedTextProvider | None = None,
) -> dict[str, int]:
    provider = provider or get_default_derived_text_provider()

    jobs = list_pending_derived_text_jobs(
        conn,
        workspace_id,
        derivation_kind=derivation_kind,
        limit=limit,
    )

    processed = 0
    skipped = 0
    errored = 0

    for job in jobs:
        try:
            if derivation_kind == "attachment_text":
                text, details = provider.extract_attachment_text(
                    conn,
                    workspace_id=workspace_id,
                    source_kind=str(job["source_kind"]),
                    source_id=str(job["source_id"]),
                )
            elif derivation_kind == "ocr_text":
                text, details = provider.extract_ocr_text(
                    conn,
                    workspace_id=workspace_id,
                    source_kind=str(job["source_kind"]),
                    source_id=str(job["source_id"]),
                )
            else:
                mark_derived_text_job_status(
                    conn,
                    job_id=int(job["id"]),
                    status="skipped",
                    error="unsupported_derivation_kind",
                )
                skipped += 1
                continue

            if not text:
                mark_derived_text_job_status(
                    conn,
                    job_id=int(job["id"]),
                    status="skipped",
                    error=str(details.get("error") or "no_text_detected"),
                )
                skipped += 1
                continue

            existing = get_derived_text(
                conn,
                workspace_id=workspace_id,
                source_kind=str(job["source_kind"]),
                source_id=str(job["source_id"]),
                derivation_kind=derivation_kind,
                extractor=str(details["extractor"]),
            )
            if existing and existing.get("text") == text:
                mark_derived_text_job_status(conn, job_id=int(job["id"]), status="done")
                skipped += 1
                continue

            provider_name = str(details.get("provider_name") or _provider_name(provider))
            metadata = {
                "job_reason": job["reason"],
                "provider": provider_name,
                **{k: v for k, v in details.items() if k not in {"extractor", "media_type", "local_path", "provider_name"}},
            }

            upsert_derived_text(
                conn,
                workspace_id=workspace_id,
                source_kind=str(job["source_kind"]),
                source_id=str(job["source_id"]),
                derivation_kind=derivation_kind,
                extractor=str(details["extractor"]),
                text=text,
                media_type=details.get("media_type"),
                local_path=details.get("local_path"),
                metadata=metadata,
            )
            mark_derived_text_job_status(conn, job_id=int(job["id"]), status="done")
            processed += 1
        except Exception as exc:  # pragma: no cover - defensive
            mark_derived_text_job_status(conn, job_id=int(job["id"]), status="error", error=str(exc))
            errored += 1

    return {"jobs": len(jobs), "processed": processed, "skipped": skipped, "errored": errored}
