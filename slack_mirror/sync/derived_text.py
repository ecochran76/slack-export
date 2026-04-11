from __future__ import annotations

import html
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Protocol
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


ExtractResult = tuple[str | None, dict]


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


def _extract_ooxml_text(path: Path) -> tuple[str | None, str | None]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        extractor = "ooxml_docx"
        members = ("word/document.xml",)
    elif suffix == ".pptx":
        extractor = "ooxml_pptx"
        members = tuple(f"ppt/slides/slide{i}.xml" for i in range(1, 512))
    elif suffix == ".xlsx":
        extractor = "ooxml_xlsx"
        members = ("xl/sharedStrings.xml",) + tuple(f"xl/worksheets/sheet{i}.xml" for i in range(1, 512))
    else:
        return None, None

    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            parts: list[str] = []
            for member in members:
                if member not in names:
                    continue
                extracted = _extract_xml_text(zf.read(member))
                if extracted:
                    parts.append(extracted)
            merged = _normalize_text(" ".join(parts))
            return (merged or None), extractor
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


_DEFAULT_PROVIDER = LocalCliDerivedTextProvider()


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

            metadata = {
                "job_reason": job["reason"],
                "provider": getattr(provider, "name", provider.__class__.__name__),
                **{k: v for k, v in details.items() if k not in {"extractor", "media_type", "local_path"}},
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
