from __future__ import annotations

import hashlib
import re
from pathlib import Path
from time import sleep

import requests


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _looks_like_html_interstitial(dest: Path) -> bool:
    try:
        head = dest.read_bytes()[:512].lstrip()
    except Exception:  # noqa: BLE001
        return False
    lowered = head.lower()
    return lowered.startswith(b"<!doctype html") or lowered.startswith(b"<html")


def classify_download_error(message: str | None) -> str:
    text = str(message or "").strip().lower()
    if not text:
        return "unknown_error"
    if "html interstitial" in text:
        return "html_interstitial"
    if "404" in text:
        return "not_found"
    if "403" in text:
        return "forbidden"
    if "401" in text:
        return "unauthorized"
    if "429" in text or "rate" in text and "limit" in text:
        return "rate_limited"
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if "ssl" in text or "certificate" in text:
        return "tls_error"
    if "connection" in text or "name resolution" in text or "temporary failure" in text:
        return "network_error"
    if re.search(r"\bmissing_scope\b", text):
        return "missing_scope"
    if re.search(r"\bfile_not_found\b", text):
        return "file_not_found"
    return "download_error"


def download_with_retries(url: str, token: str, dest: Path, retries: int = 3) -> tuple[bool, str | None]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {token}"}
    last_err: str | None = None
    for i in range(retries):
        try:
            with requests.get(url, headers=headers, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                with dest.open("wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            if _looks_like_html_interstitial(dest):
                dest.unlink(missing_ok=True)
                raise ValueError("downloaded HTML interstitial instead of file content")
            return True, sha256_file(dest)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            if i < retries - 1:
                sleep(1.0 * (i + 1))
    return False, last_err
