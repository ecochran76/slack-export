from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import quote


_DEFAULT_EXPORT_ROOT = Path("~/.local/share/slack-mirror/exports").expanduser()
_EXPORT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _config_value(config: Any, key: str, default: Any = None) -> Any:
    if hasattr(config, "get"):
        return config.get(key, default)
    if isinstance(config, dict):
        return config.get(key, default)
    return default


def slugify(value: str, *, max_length: int = 24) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if not cleaned:
        cleaned = "export"
    return cleaned[:max_length].rstrip("-") or "export"


def validate_export_id(export_id: str) -> str:
    value = str(export_id or "").strip()
    if not value or not _EXPORT_ID_RE.fullmatch(value):
        raise ValueError(f"Invalid export id: {export_id}")
    return value


def build_export_id(
    kind: str,
    *,
    workspace: str,
    channel: str | None = None,
    day: str | None = None,
    descriptor: str | None = None,
    seed_extra: dict[str, Any] | None = None,
) -> str:
    seed = {
        "kind": kind,
        "workspace": workspace,
        "channel": channel,
        "day": day,
        "descriptor": descriptor,
        "extra": seed_extra or {},
    }
    digest = hashlib.blake2s(
        json.dumps(seed, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        digest_size=5,
    ).hexdigest()
    parts = [
        slugify(kind, max_length=16),
        slugify(workspace, max_length=16),
    ]
    if channel:
        parts.append(slugify(channel, max_length=20))
    if day:
        parts.append(slugify(day, max_length=16))
    if descriptor:
        parts.append(slugify(descriptor, max_length=20))
    label = "-".join(part for part in parts if part)
    label = label[:52].rstrip("-")
    return f"{label}-{digest}"


def resolve_export_root(config: Any) -> Path:
    exports = _config_value(config, "exports", {}) or {}
    raw = exports.get("root_dir")
    path = Path(raw).expanduser() if raw else _DEFAULT_EXPORT_ROOT
    return path.resolve()


def resolve_export_base_url(config: Any, *, audience: str = "local") -> str | None:
    exports = _config_value(config, "exports", {}) or {}
    if audience == "external":
        value = exports.get("external_base_url") or exports.get("public_base_url")
    else:
        value = exports.get("local_base_url") or exports.get("public_base_url")
    if not value:
        return None
    return str(value).rstrip("/")


def resolve_export_base_urls(config: Any) -> dict[str, str]:
    urls: dict[str, str] = {}
    for audience in ("local", "external"):
        value = resolve_export_base_url(config, audience=audience)
        if value:
            urls[audience] = value
    return urls


def build_export_url(base_url: str, export_id: str, relpath: str, *, preview: bool = False) -> str:
    parts = [quote(part) for part in Path(relpath).parts if part not in {"", ".", ".."}]
    suffix = "/".join(parts)
    base = f"{base_url.rstrip('/')}/exports/{quote(export_id)}"
    if suffix:
        base = f"{base}/{suffix}"
    if preview:
        base = f"{base}/preview"
    return base


def select_export_url(urls: dict[str, str], audience: str = "local") -> str | None:
    if audience in urls:
        return urls[audience]
    if "local" in urls:
        return urls["local"]
    if "external" in urls:
        return urls["external"]
    return next(iter(urls.values()), None)


def build_export_urls(base_urls: dict[str, str], export_id: str, relpath: str, *, preview: bool = False) -> dict[str, str]:
    return {
        audience: build_export_url(base_url, export_id, relpath, preview=preview)
        for audience, base_url in base_urls.items()
    }


def safe_export_path(export_root: Path, export_id: str, relpath: str) -> Path:
    base = (export_root / validate_export_id(export_id)).resolve()
    target = (base / relpath).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"export path escapes bundle root: {relpath}")
    return target


def delete_export_bundle(export_root: Path, export_id: str) -> bool:
    safe_export_id = validate_export_id(export_id)
    bundle_dir = export_root / safe_export_id
    if not bundle_dir.exists() or not bundle_dir.is_dir():
        return False
    shutil.rmtree(bundle_dir)
    return True


def _replace_bundle_urls(text: str, *, old_export_id: str, new_export_id: str) -> str:
    return text.replace(f"/exports/{old_export_id}/", f"/exports/{new_export_id}/").replace(
        f"/exports/{old_export_id}\"",
        f"/exports/{new_export_id}\"",
    )


def _rewrite_export_payload_urls(value: Any, *, old_export_id: str, new_export_id: str) -> Any:
    if isinstance(value, dict):
        updated = {}
        for key, item in value.items():
            if key == "export_id":
                updated[key] = new_export_id
            else:
                updated[key] = _rewrite_export_payload_urls(item, old_export_id=old_export_id, new_export_id=new_export_id)
        return updated
    if isinstance(value, list):
        return [_rewrite_export_payload_urls(item, old_export_id=old_export_id, new_export_id=new_export_id) for item in value]
    if isinstance(value, str):
        return _replace_bundle_urls(value, old_export_id=old_export_id, new_export_id=new_export_id)
    return value


def rename_export_bundle(
    export_root: Path,
    *,
    export_id: str,
    new_export_id: str,
    base_urls: dict[str, str],
    default_audience: str = "local",
) -> dict[str, Any]:
    safe_export_id = validate_export_id(export_id)
    safe_new_export_id = validate_export_id(new_export_id)
    source_dir = export_root / safe_export_id
    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(f"export bundle not found: {safe_export_id}")
    if safe_export_id == safe_new_export_id:
        return build_export_manifest(
            source_dir,
            export_id=safe_export_id,
            base_urls=base_urls,
            default_audience=default_audience,
        )
    target_dir = export_root / safe_new_export_id
    if target_dir.exists():
        raise FileExistsError(f"export bundle already exists: {safe_new_export_id}")
    shutil.move(str(source_dir), str(target_dir))

    channel_day_path = target_dir / "channel-day.json"
    if channel_day_path.exists():
        payload = json.loads(channel_day_path.read_text(encoding="utf-8"))
        rewritten = _rewrite_export_payload_urls(payload, old_export_id=safe_export_id, new_export_id=safe_new_export_id)
        channel_day_path.write_text(json.dumps(rewritten, indent=2), encoding="utf-8")

    index_path = target_dir / "index.html"
    if index_path.exists():
        html = index_path.read_text(encoding="utf-8")
        index_path.write_text(
            _replace_bundle_urls(html, old_export_id=safe_export_id, new_export_id=safe_new_export_id),
            encoding="utf-8",
        )

    manifest = build_export_manifest(
        target_dir,
        export_id=safe_new_export_id,
        base_urls=base_urls,
        default_audience=default_audience,
    )
    (target_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def preview_supported_for_path(path: Path, *, content_type: str | None = None) -> bool:
    detected = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return (
        detected.startswith("image/")
        or detected == "application/pdf"
        or detected == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or detected == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        or detected == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        or detected == "application/vnd.oasis.opendocument.text"
        or detected == "application/vnd.oasis.opendocument.presentation"
        or detected == "application/vnd.oasis.opendocument.spreadsheet"
        or detected.startswith("text/")
        or detected in {"application/json", "application/xml"}
    )


def read_export_metadata(bundle_dir: Path) -> dict[str, Any]:
    manifest_path = bundle_dir / "manifest.json"
    if manifest_path.exists():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

    channel_day_path = bundle_dir / "channel-day.json"
    if channel_day_path.exists():
        try:
            payload = json.loads(channel_day_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return {
                    "kind": "channel-day",
                    "workspace": payload.get("workspace"),
                    "channel": payload.get("channel"),
                    "channel_id": payload.get("channel_id"),
                    "day": payload.get("day"),
                    "tz": payload.get("tz"),
                    "export_id": payload.get("export_id") or bundle_dir.name,
                }
        except Exception:
            pass

    return {"export_id": bundle_dir.name}


def build_export_manifest(
    bundle_dir: Path,
    *,
    export_id: str,
    base_urls: dict[str, str],
    default_audience: str = "local",
) -> dict[str, Any]:
    metadata = read_export_metadata(bundle_dir)
    bundle_urls = {
        audience: f"{base_url.rstrip('/')}/exports/{quote(export_id)}"
        for audience, base_url in base_urls.items()
    }
    files: list[dict[str, Any]] = []
    attachment_count = 0
    for path in sorted(p for p in bundle_dir.rglob("*") if p.is_file()):
        relpath = path.relative_to(bundle_dir).as_posix()
        if relpath == "manifest.json":
            continue
        content_type, _ = mimetypes.guess_type(str(path))
        content_type = content_type or "application/octet-stream"
        download_urls = build_export_urls(base_urls, export_id, relpath)
        preview_urls = (
            build_export_urls(base_urls, export_id, relpath, preview=True)
            if preview_supported_for_path(path, content_type=content_type)
            else {}
        )
        role = "attachment" if relpath.startswith("attachments/") else "bundle_file"
        if role == "attachment":
            attachment_count += 1
        files.append(
            {
                "relpath": relpath,
                "role": role,
                "content_type": content_type,
                "size_bytes": path.stat().st_size,
                "download_urls": download_urls,
                "preview_urls": preview_urls,
                "download_url": select_export_url(download_urls, default_audience),
                "preview_url": select_export_url(preview_urls, default_audience),
            }
        )

    return {
        "export_id": export_id,
        "kind": metadata.get("kind") or "export-bundle",
        "workspace": metadata.get("workspace"),
        "channel": metadata.get("channel"),
        "channel_id": metadata.get("channel_id"),
        "day": metadata.get("day"),
        "tz": metadata.get("tz"),
        "default_audience": default_audience,
        "bundle_urls": bundle_urls,
        "bundle_url": select_export_url(bundle_urls, default_audience),
        "file_count": len(files),
        "attachment_count": attachment_count,
        "files": files,
    }


def list_export_manifests(
    export_root: Path,
    *,
    base_urls: dict[str, str],
    default_audience: str = "local",
) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    if not export_root.exists():
        return manifests
    for bundle_dir in sorted((p for p in export_root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
        manifests.append(
            build_export_manifest(
                bundle_dir,
                export_id=bundle_dir.name,
                base_urls=base_urls,
                default_audience=default_audience,
            )
        )
    return manifests
