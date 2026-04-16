from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from slack_mirror.core.config import load_config, resolve_config_path
from slack_mirror.core.db import apply_migrations, connect, get_workspace_by_name, upsert_workspace

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")
_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,62}$")
_DOMAIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,80}$")

_CREDENTIAL_FIELDS = (
    ("team_id", "TEAM_ID", False),
    ("token", "BOT_TOKEN", True),
    ("outbound_token", "WRITE_BOT_TOKEN", True),
    ("user_token", "USER_TOKEN", False),
    ("outbound_user_token", "WRITE_USER_TOKEN", False),
    ("app_token", "APP_TOKEN", True),
    ("signing_secret", "SIGNING_SECRET", True),
)


@dataclass(frozen=True)
class TenantOnboardResult:
    tenant: dict[str, Any]
    changed: bool
    config_path: str
    backup_path: str | None
    manifest_path: str
    dry_run: bool


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _migrations_dir() -> Path:
    return _repo_root() / "slack_mirror" / "core" / "migrations"


def _default_manifest_template() -> Path:
    return _repo_root() / "manifests" / "slack-mirror-socket-mode.json"


def _default_manifest_output(name: str) -> Path:
    return _repo_root() / "manifests" / f"slack-mirror-socket-mode-{name}.rendered.json"


def normalize_tenant_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", str(name or "").strip().casefold()).strip("-_")
    if not _NAME_PATTERN.fullmatch(normalized):
        raise ValueError(
            "tenant name must start with a letter and contain only lowercase letters, digits, '-' or '_'"
        )
    return normalized


def normalize_slack_domain(domain: str) -> str:
    value = str(domain or "").strip().casefold()
    if value.startswith("https://") or value.startswith("http://"):
        from urllib.parse import urlparse

        host = urlparse(value).netloc
        value = host.split(".slack.com", 1)[0]
    value = value.removesuffix(".slack.com").strip(".")
    if not _DOMAIN_PATTERN.fullmatch(value):
        raise ValueError("slack domain must be the workspace subdomain, for example 'acme-team'")
    return value


def tenant_env_prefix(name: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "_", normalize_tenant_name(name).upper()).strip("_")
    return f"SLACK_{slug}"


def tenant_credential_placeholders(name: str) -> dict[str, str]:
    prefix = tenant_env_prefix(name)
    return {field: f"{prefix}_{suffix}" for field, suffix, _required in _CREDENTIAL_FIELDS}


def tenant_workspace_scaffold(name: str, domain: str) -> dict[str, Any]:
    placeholders = tenant_credential_placeholders(name)
    return {
        "name": normalize_tenant_name(name),
        "domain": normalize_slack_domain(domain),
        "team_id": f"${{{placeholders['team_id']}:-}}",
        "token": f"${{{placeholders['token']}:-}}",
        "outbound_token": f"${{{placeholders['outbound_token']}:-}}",
        "user_token": f"${{{placeholders['user_token']}:-}}",
        "outbound_user_token": f"${{{placeholders['outbound_user_token']}:-}}",
        "app_token": f"${{{placeholders['app_token']}:-}}",
        "signing_secret": f"${{{placeholders['signing_secret']}:-}}",
        "enabled": False,
    }


def _load_raw_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    return data


def _write_raw_config(path: Path, data: dict[str, Any]) -> None:
    rendered = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    path.write_text(rendered, encoding="utf-8")


def _find_workspace(raw_config: dict[str, Any], name: str) -> dict[str, Any] | None:
    for item in raw_config.get("workspaces") or []:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def _env_placeholder(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = _ENV_PATTERN.fullmatch(value.strip())
    return match.group(1) if match else None


def _has_secretish_value(value: Any) -> bool:
    return bool(str(value or "").strip())


def _credential_status(raw_ws: dict[str, Any] | None, expanded_ws: dict[str, Any] | None) -> dict[str, Any]:
    placeholders = {}
    presence = {}
    missing_required = []
    for field, _suffix, required in _CREDENTIAL_FIELDS:
        placeholder = _env_placeholder((raw_ws or {}).get(field))
        if placeholder:
            placeholders[field] = placeholder
        expanded_present = _has_secretish_value((expanded_ws or {}).get(field))
        env_present = bool(placeholder and _has_secretish_value(os.environ.get(placeholder)))
        present = bool(expanded_present or env_present)
        presence[field] = {
            "required": required,
            "present": present,
            "source": "env" if env_present else "config" if expanded_present else "missing",
            "env": placeholder,
        }
        if required and not present:
            missing_required.append(field)
    return {
        "placeholders": placeholders,
        "presence": presence,
        "missing_required": missing_required,
        "ready": not missing_required,
    }


def _db_synced(config_path: str | Path | None, name: str) -> bool:
    try:
        cfg = load_config(config_path)
        db_path = cfg.get("storage", {}).get("db_path", "./data/slack_mirror.db")
        conn = connect(db_path)
        apply_migrations(conn, str(_migrations_dir()))
        return get_workspace_by_name(conn, name) is not None
    except Exception:
        return False


def _manifest_status(name: str, manifest_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser() if manifest_path else _default_manifest_output(name)
    if not path.is_absolute():
        path = (_repo_root() / path).resolve()
    return {"path": str(path), "exists": path.exists()}


def tenant_status(
    *,
    config_path: str | Path | None = None,
    name: str | None = None,
) -> list[dict[str, Any]]:
    resolved = resolve_config_path(config_path)
    raw = _load_raw_config(resolved)
    expanded = load_config(resolved)
    raw_workspaces = [item for item in raw.get("workspaces") or [] if isinstance(item, dict)]
    expanded_workspaces = [
        item for item in expanded.get("workspaces", []) if isinstance(item, dict) and item.get("name")
    ]
    expanded_by_name = {str(item.get("name")): item for item in expanded_workspaces}
    selected_name = normalize_tenant_name(name) if name else None
    rows = []
    for raw_ws in raw_workspaces:
        ws_name = str(raw_ws.get("name") or "").strip()
        if not ws_name:
            continue
        if selected_name and ws_name != selected_name:
            continue
        expanded_ws = expanded_by_name.get(ws_name, {})
        credentials = _credential_status(raw_ws, expanded_ws)
        enabled = bool(expanded_ws.get("enabled", raw_ws.get("enabled", True)) is not False)
        synced = _db_synced(resolved, ws_name)
        next_action = "ready_to_activate"
        if enabled:
            next_action = "monitor_live_validation"
        elif not credentials["ready"]:
            next_action = "credentials_required"
        elif not synced:
            next_action = "sync_config"
        rows.append(
            {
                "name": ws_name,
                "domain": expanded_ws.get("domain") or raw_ws.get("domain") or "",
                "enabled": enabled,
                "db_synced": synced,
                "credential_placeholders": credentials["placeholders"],
                "credential_presence": credentials["presence"],
                "credential_ready": credentials["ready"],
                "missing_required_credentials": credentials["missing_required"],
                "manifest": _manifest_status(ws_name),
                "validation_status": "unknown",
                "live_units": {"webhooks": "unknown", "daemon": "unknown"},
                "next_action": next_action,
            }
        )
    if selected_name and not rows:
        raise ValueError(f"Tenant '{selected_name}' not found in config")
    return rows


def _expand_manifest_template(text: str, values: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        fallback = match.group(2)
        return values.get(key, os.getenv(key, fallback if fallback is not None else ""))

    return _ENV_PATTERN.sub(repl, text)


def render_tenant_manifest(
    *,
    name: str,
    display_name: str | None = None,
    template_path: str | Path | None = None,
    output_path: str | Path | None = None,
    dry_run: bool = False,
) -> Path:
    tenant_name = normalize_tenant_name(name)
    template = Path(template_path).expanduser() if template_path else _default_manifest_template()
    if not template.is_absolute():
        template = (_repo_root() / template).resolve()
    output = Path(output_path).expanduser() if output_path else _default_manifest_output(tenant_name)
    if not output.is_absolute():
        output = (_repo_root() / output).resolve()
    app_label = display_name or tenant_name.replace("-", " ").replace("_", " ").title()
    values = {
        "SLACK_MIRROR_APP_NAME": f"Slack Mirror {app_label}",
        "SLACK_MIRROR_APP_DESCRIPTION": f"Dedicated Slack Mirror app for {app_label}",
        "SLACK_MIRROR_BOT_DISPLAY_NAME": "Slack Mirror",
        "SLACK_MIRROR_REDIRECT_URL": "https://localhost:3000/slack/oauth/callback",
    }
    rendered = _expand_manifest_template(template.read_text(encoding="utf-8"), values)
    json.loads(rendered)
    if not dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    return output


def scaffold_tenant(
    *,
    config_path: str | Path | None = None,
    name: str,
    domain: str,
    display_name: str | None = None,
    manifest_path: str | Path | None = None,
    dry_run: bool = False,
    sync_db: bool = True,
) -> TenantOnboardResult:
    tenant_name = normalize_tenant_name(name)
    slack_domain = normalize_slack_domain(domain)
    resolved = resolve_config_path(config_path)
    raw = _load_raw_config(resolved)
    workspaces = raw.setdefault("workspaces", [])
    if not isinstance(workspaces, list):
        raise ValueError("config workspaces must be a list")

    existing = _find_workspace(raw, tenant_name)
    scaffold = tenant_workspace_scaffold(tenant_name, slack_domain)
    changed = False
    if existing is None:
        workspaces.append(scaffold)
        changed = True
    else:
        existing_domain = normalize_slack_domain(str(existing.get("domain") or slack_domain))
        if existing_domain != slack_domain:
            raise ValueError(
                f"Tenant '{tenant_name}' already exists with domain '{existing.get('domain')}', not '{slack_domain}'"
            )
        for key, value in scaffold.items():
            if key not in existing:
                existing[key] = value
                changed = True
        if existing.get("enabled", False) is not False:
            raise ValueError(f"Tenant '{tenant_name}' already exists and is enabled")

    manifest = render_tenant_manifest(
        name=tenant_name,
        display_name=display_name,
        output_path=manifest_path,
        dry_run=dry_run,
    )

    backup_path: str | None = None
    if changed and not dry_run:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = resolved.with_name(f"{resolved.name}.before-{tenant_name}-{timestamp}")
        shutil.copy2(resolved, backup)
        _write_raw_config(resolved, raw)
        # Re-read through the normal loader so invalid YAML/env path issues are caught immediately.
        load_config(resolved)
        backup_path = str(backup)

    if sync_db and not dry_run:
        cfg = load_config(resolved)
        db_path = cfg.get("storage", {}).get("db_path", "./data/slack_mirror.db")
        conn = connect(db_path)
        apply_migrations(conn, str(_migrations_dir()))
        for ws in cfg.get("workspaces", []):
            if ws.get("name") == tenant_name:
                upsert_workspace(
                    conn,
                    name=tenant_name,
                    team_id=ws.get("team_id"),
                    domain=ws.get("domain"),
                    config=ws,
                )
                break

    if not dry_run:
        status = tenant_status(config_path=resolved, name=tenant_name)[0]
    elif existing is not None:
        status = tenant_status(config_path=resolved, name=tenant_name)[0]
        status["manifest"] = _manifest_status(tenant_name, manifest)
    else:
        status = {
            "name": tenant_name,
            "domain": slack_domain,
            "enabled": False,
            "db_synced": False,
            "credential_placeholders": tenant_credential_placeholders(tenant_name),
            "credential_ready": False,
            "missing_required_credentials": [field for field, _suffix, required in _CREDENTIAL_FIELDS if required],
            "manifest": _manifest_status(tenant_name, manifest),
            "next_action": "credentials_required",
        }
    return TenantOnboardResult(
        tenant=status,
        changed=changed,
        config_path=str(resolved),
        backup_path=backup_path,
        manifest_path=str(manifest),
        dry_run=dry_run,
    )
