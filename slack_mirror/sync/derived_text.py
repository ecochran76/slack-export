from __future__ import annotations

import html
import re
import shutil
import subprocess
from pathlib import Path

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


def _extract_attachment_text(conn, *, workspace_id: int, source_kind: str, source_id: str) -> tuple[str | None, dict]:
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


def process_derived_text_jobs(
    conn,
    *,
    workspace_id: int,
    derivation_kind: str = "attachment_text",
    limit: int = 100,
) -> dict[str, int]:
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
            if derivation_kind != "attachment_text":
                mark_derived_text_job_status(
                    conn,
                    job_id=int(job["id"]),
                    status="skipped",
                    error="unsupported_derivation_kind",
                )
                skipped += 1
                continue

            text, details = _extract_attachment_text(
                conn,
                workspace_id=workspace_id,
                source_kind=str(job["source_kind"]),
                source_id=str(job["source_id"]),
            )
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
                metadata={"job_reason": job["reason"]},
            )
            mark_derived_text_job_status(conn, job_id=int(job["id"]), status="done")
            processed += 1
        except Exception as exc:  # pragma: no cover - defensive
            mark_derived_text_job_status(conn, job_id=int(job["id"]), status="error", error=str(exc))
            errored += 1

    return {"jobs": len(jobs), "processed": processed, "skipped": skipped, "errored": errored}
