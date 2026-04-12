from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote


_DEFAULT_EXPORT_ROOT = Path("~/.local/share/slack-mirror/exports").expanduser()


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


def build_export_url(base_url: str, export_id: str, relpath: str, *, preview: bool = False) -> str:
    parts = [quote(part) for part in Path(relpath).parts if part not in {"", ".", ".."}]
    suffix = "/".join(parts)
    base = f"{base_url.rstrip('/')}/exports/{quote(export_id)}"
    if suffix:
        base = f"{base}/{suffix}"
    if preview:
        base = f"{base}/preview"
    return base


def safe_export_path(export_root: Path, export_id: str, relpath: str) -> Path:
    base = (export_root / export_id).resolve()
    target = (base / relpath).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"export path escapes bundle root: {relpath}")
    return target
