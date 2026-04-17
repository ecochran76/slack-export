from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from slack_mirror.core.config import load_config, resolve_config_path
from slack_mirror.core.db import apply_migrations, connect, get_workspace_by_name, upsert_workspace
from slack_mirror.service.runtime_heartbeat import load_reconcile_state
from slack_mirror.service.user_env import _systemctl_state

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


@dataclass(frozen=True)
class TenantActivateResult:
    tenant: dict[str, Any]
    changed: bool
    config_path: str
    backup_path: str | None
    live_units_installed: bool
    live_unit_command: list[str] | None
    dry_run: bool


@dataclass(frozen=True)
class TenantCredentialInstallResult:
    tenant: dict[str, Any]
    changed: bool
    dotenv_path: str
    backup_path: str | None
    installed_keys: list[str]
    skipped_keys: list[str]
    dry_run: bool


@dataclass(frozen=True)
class TenantRetireResult:
    tenant: dict[str, Any]
    changed: bool
    config_path: str
    backup_path: str | None
    db_deleted: bool
    db_counts: dict[str, int]
    live_unit_commands: list[list[str]]
    dry_run: bool


@dataclass(frozen=True)
class TenantCommandResult:
    tenant: dict[str, Any]
    action: str
    commands: list[list[str]]
    dry_run: bool


RunFn = Callable[..., subprocess.CompletedProcess]


def _repo_root() -> Path:
    package_root = Path(__file__).resolve().parents[2]
    if (package_root / "manifests" / "slack-mirror-socket-mode.json").exists():
        return package_root
    managed_app = Path.home() / ".local" / "share" / "slack-mirror" / "app"
    if (managed_app / "manifests" / "slack-mirror-socket-mode.json").exists():
        return managed_app
    return package_root


def _migrations_dir() -> Path:
    return _repo_root() / "slack_mirror" / "core" / "migrations"


def _default_manifest_template() -> Path:
    return _repo_root() / "manifests" / "slack-mirror-socket-mode.json"


def _default_manifest_output(name: str) -> Path:
    return _repo_root() / "manifests" / f"slack-mirror-socket-mode-{name}.rendered.json"


def _live_install_script() -> Path:
    return _repo_root() / "scripts" / "install_live_mode_systemd_user.sh"


def _run_checked_command(command: list[str], *, runner: RunFn, failure_hint: str) -> None:
    try:
        if runner is subprocess.run:
            runner(command, check=True, text=True, capture_output=True)
        else:
            runner(command, check=True)
    except subprocess.CalledProcessError as exc:
        stderr = str(getattr(exc, "stderr", "") or "").strip()
        stdout = str(getattr(exc, "stdout", "") or "").strip()
        detail = stderr or stdout
        if detail:
            detail = detail.splitlines()[-1]
            raise RuntimeError(f"{failure_hint}: {detail}") from exc
        raise RuntimeError(failure_hint) from exc


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


def _backup_config(path: Path, *, tenant_name: str, operation: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.before-{tenant_name}-{operation}-{timestamp}")
    shutil.copy2(path, backup)
    return backup


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


def _dotenv_path_for_config(raw_config: dict[str, Any], config_path: Path) -> Path:
    dotenv = str(raw_config.get("dotenv") or "").strip()
    if not dotenv:
        raise ValueError("config does not define dotenv; add a dotenv path before installing credentials")
    path = Path(dotenv).expanduser()
    if not path.is_absolute():
        path = (config_path.parent / path).resolve()
    return path


def _backup_dotenv(path: Path, *, tenant_name: str) -> Path | None:
    if not path.exists():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.before-{tenant_name}-credentials-{timestamp}")
    shutil.copy2(path, backup)
    return backup


def _quote_dotenv_value(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _upsert_dotenv_values(path: Path, values: dict[str, str], *, dry_run: bool) -> bool:
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    key_pattern = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
    seen: set[str] = set()
    changed = False
    output: list[str] = []
    for line in existing_lines:
        match = key_pattern.match(line.strip())
        key = match.group(1) if match else None
        if key in values:
            next_line = f"{key}={_quote_dotenv_value(values[key])}"
            output.append(next_line)
            seen.add(key)
            changed = changed or line != next_line
        else:
            output.append(line)
    missing = [key for key in values if key not in seen]
    if missing and output and output[-1].strip():
        output.append("")
    for key in missing:
        output.append(f"{key}={_quote_dotenv_value(values[key])}")
        changed = True
    if changed and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    return changed


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


def _sync_tenant_to_db(config_path: str | Path, name: str) -> None:
    cfg = load_config(config_path)
    db_path = cfg.get("storage", {}).get("db_path", "./data/slack_mirror.db")
    conn = connect(db_path)
    apply_migrations(conn, str(_migrations_dir()))
    for ws in cfg.get("workspaces", []):
        if ws.get("name") == name:
            upsert_workspace(
                conn,
                name=name,
                team_id=ws.get("team_id"),
                domain=ws.get("domain"),
                config=ws,
            )
            return
    raise ValueError(f"Tenant '{name}' not found in expanded config")


def _tenant_db_counts(conn, workspace_id: int) -> dict[str, int]:
    tables = (
        "users",
        "channels",
        "messages",
        "files",
        "canvases",
        "events",
        "sync_state",
        "content_chunks",
        "embeddings",
        "channel_members",
        "message_embeddings",
        "embedding_jobs",
        "outbound_actions",
        "listeners",
        "listener_deliveries",
        "derived_text",
        "derived_text_jobs",
        "derived_text_chunks",
    )
    counts: dict[str, int] = {}
    for table in tables:
        try:
            row = conn.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE workspace_id = ?", (workspace_id,)).fetchone()
        except Exception:
            continue
        counts[table] = int(row["c"] if row else 0)
    return counts


def _delete_tenant_db_rows(config_path: str | Path, name: str, *, dry_run: bool) -> tuple[bool, dict[str, int]]:
    cfg = load_config(config_path)
    db_path = cfg.get("storage", {}).get("db_path", "./data/slack_mirror.db")
    conn = connect(db_path)
    apply_migrations(conn, str(_migrations_dir()))
    row = get_workspace_by_name(conn, name)
    if row is None:
        return False, {}
    workspace_id = int(row["id"])
    counts = _tenant_db_counts(conn, workspace_id)
    if dry_run:
        return True, counts
    with conn:
        # FTS tables are virtual and are not covered by ON DELETE CASCADE.
        conn.execute("DELETE FROM messages_fts WHERE workspace_id = ?", (workspace_id,))
        conn.execute("DELETE FROM content_chunks_fts WHERE workspace_name = ?", (name,))
        conn.execute("DELETE FROM derived_text_fts WHERE workspace_id = ?", (workspace_id,))
        conn.execute("DELETE FROM derived_text_chunks_fts WHERE workspace_id = ?", (workspace_id,))
        # Some operational tables predate workspace FKs; remove them explicitly.
        for table in (
            "listener_deliveries",
            "listeners",
            "outbound_actions",
            "derived_text_chunks",
            "derived_text_jobs",
            "derived_text",
            "embedding_jobs",
            "message_embeddings",
            "channel_members",
            "embeddings",
            "content_chunks",
            "events",
            "sync_state",
            "files",
            "canvases",
            "messages",
            "users",
            "channels",
        ):
            conn.execute(f"DELETE FROM {table} WHERE workspace_id = ?", (workspace_id,))
        conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
    return True, counts


def _tenant_live_units(name: str) -> list[str]:
    tenant_name = normalize_tenant_name(name)
    return [f"slack-mirror-webhooks-{tenant_name}.service", f"slack-mirror-daemon-{tenant_name}.service"]


def _systemctl_user_command(action: str, name: str) -> list[str]:
    if action not in {"restart", "stop"}:
        raise ValueError(f"unsupported live unit action: {action}")
    return ["systemctl", "--user", action, *_tenant_live_units(name)]


def _slack_mirror_command(config_path: str | Path) -> list[str]:
    wrapper = shutil.which("slack-mirror-user")
    managed_config = (Path.home() / ".config" / "slack-mirror" / "config.yaml").resolve()
    try:
        if wrapper and Path(config_path).expanduser().resolve() == managed_config:
            return [wrapper]
    except FileNotFoundError:
        pass
    console = shutil.which("slack-mirror")
    if console:
        return [console, "--config", str(resolve_config_path(config_path))]
    return [sys.executable, "-m", "slack_mirror.cli.main", "--config", str(resolve_config_path(config_path))]


def _manifest_status(name: str, manifest_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser() if manifest_path else _default_manifest_output(name)
    if not path.is_absolute():
        path = (_repo_root() / path).resolve()
    return {"path": str(path), "exists": path.exists()}


def _tenant_live_unit_states(name: str) -> dict[str, str]:
    webhooks_unit, daemon_unit = _tenant_live_units(name)
    return {
        "webhooks": _systemctl_state(subprocess.run, webhooks_unit),
        "daemon": _systemctl_state(subprocess.run, daemon_unit),
    }


def _tenant_db_stats(config_path: Path, name: str) -> dict[str, Any]:
    expanded = load_config(config_path)
    db_path = Path(str(expanded.get("storage", {}).get("db_path") or "")).expanduser()
    if not db_path.exists():
        return {
            "present": False,
            "channels": 0,
            "messages": 0,
            "files": 0,
            "attachment_text": 0,
            "ocr_text": 0,
            "embedding_pending": 0,
            "embedding_errors": 0,
            "derived_pending": 0,
            "derived_errors": 0,
        }
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM channels c JOIN workspaces w ON w.id = c.workspace_id WHERE w.name = ?) AS channels,
              (SELECT COUNT(*) FROM messages m JOIN workspaces w ON w.id = m.workspace_id WHERE w.name = ? AND m.deleted = 0) AS messages,
              (SELECT COUNT(*) FROM files f JOIN workspaces w ON w.id = f.workspace_id WHERE w.name = ?) AS files,
              (SELECT COUNT(*) FROM derived_text dt JOIN workspaces w ON w.id = dt.workspace_id WHERE w.name = ? AND dt.derivation_kind = 'attachment_text') AS attachment_text,
              (SELECT COUNT(*) FROM derived_text dt JOIN workspaces w ON w.id = dt.workspace_id WHERE w.name = ? AND dt.derivation_kind = 'ocr_text') AS ocr_text,
              (SELECT COUNT(*) FROM embedding_jobs ej JOIN workspaces w ON w.id = ej.workspace_id WHERE w.name = ? AND ej.status = 'pending') AS embedding_pending,
              (SELECT COUNT(*) FROM embedding_jobs ej JOIN workspaces w ON w.id = ej.workspace_id WHERE w.name = ? AND ej.status = 'error') AS embedding_errors,
              (SELECT COUNT(*) FROM derived_text_jobs dj JOIN workspaces w ON w.id = dj.workspace_id WHERE w.name = ? AND dj.status = 'pending') AS derived_pending,
              (SELECT COUNT(*) FROM derived_text_jobs dj JOIN workspaces w ON w.id = dj.workspace_id WHERE w.name = ? AND dj.status = 'error') AS derived_errors
            """,
            (name, name, name, name, name, name, name, name, name),
        ).fetchone()
        return {
            "present": True,
            "channels": int(row["channels"] or 0),
            "messages": int(row["messages"] or 0),
            "files": int(row["files"] or 0),
            "attachment_text": int(row["attachment_text"] or 0),
            "ocr_text": int(row["ocr_text"] or 0),
            "embedding_pending": int(row["embedding_pending"] or 0),
            "embedding_errors": int(row["embedding_errors"] or 0),
            "derived_pending": int(row["derived_pending"] or 0),
            "derived_errors": int(row["derived_errors"] or 0),
        }
    finally:
        conn.close()


def _tenant_sync_health(*, config_path: Path, name: str, enabled: bool) -> dict[str, Any]:
    reconcile_state = load_reconcile_state(config_path, workspace=name, auth_mode="user")
    if not enabled:
        return {
            "label": "disabled",
            "tone": "neutral",
            "summary": "Tenant is disabled. Activate it after credentials are installed.",
            "detail": "No live validation is expected while the tenant is disabled.",
            "reconcile": {
                "state_present": False,
                "attempted": 0,
                "downloaded": 0,
                "warnings": 0,
                "failed": 0,
            },
        }
    if not reconcile_state:
        return {
            "label": "needs_initial_sync",
            "tone": "warn",
            "summary": "Initial history sync has not run yet.",
            "detail": "Run initial sync to seed mirrored history and establish reconcile state.",
            "reconcile": {
                "state_present": False,
                "attempted": 0,
                "downloaded": 0,
                "warnings": 0,
                "failed": 0,
            },
        }
    attempted = int(reconcile_state.get("attempted") or 0)
    downloaded = int(reconcile_state.get("downloaded") or 0)
    warnings = int(reconcile_state.get("warnings") or 0)
    failed = int(reconcile_state.get("failed") or 0)
    if failed:
        label = "error"
        tone = "bad"
        summary = f"Last reconcile recorded {failed} failure(s)."
    elif warnings:
        label = "warning"
        tone = "warn"
        summary = f"Last reconcile recorded {warnings} warning(s)."
    elif downloaded or attempted:
        label = "healthy"
        tone = "ok"
        summary = f"Last reconcile downloaded {downloaded} item(s) across {attempted} attempt(s)."
    else:
        label = "idle"
        tone = "neutral"
        summary = "Reconcile state exists but no recent sync work was recorded."
    return {
        "label": label,
        "tone": tone,
        "summary": summary,
        "detail": str(reconcile_state.get("iso_utc") or "") or "No reconcile timestamp recorded.",
        "reconcile": {
            "state_present": True,
            "attempted": attempted,
            "downloaded": downloaded,
            "warnings": warnings,
            "failed": failed,
        },
    }


def _tenant_validation_status(
    *,
    enabled: bool,
    credential_ready: bool,
    db_synced: bool,
    live_units: dict[str, str],
    sync_health: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if not enabled:
        return (
            "disabled",
            {
                "tone": "warn" if credential_ready else "neutral",
                "summary": "Tenant is disabled.",
                "detail": "Activate the tenant to start live sync and validation.",
            },
        )
    if not credential_ready:
        return (
            "credentials_required",
            {
                "tone": "bad",
                "summary": "Required credentials are missing.",
                "detail": "Install the missing Slack credentials before activation or live sync.",
            },
        )
    if not db_synced:
        return (
            "db_sync_required",
            {
                "tone": "warn",
                "summary": "Config is not synced into the DB.",
                "detail": "Run workspace sync or re-activate the tenant so DB state matches config.",
            },
        )
    live_states = {str(value or "unknown") for value in live_units.values()}
    if "failed" in live_states:
        return (
            "live_error",
            {
                "tone": "bad",
                "summary": "One or more live units are failed.",
                "detail": "Restart the failed live unit and inspect its journal if it does not recover.",
            },
        )
    if "active" not in live_states:
        return (
            "live_stopped",
            {
                "tone": "warn",
                "summary": "Live sync is not running.",
                "detail": "Start or install live sync to restore steady-state ingest.",
            },
        )
    sync_label = str(sync_health.get("label") or "")
    sync_tone = str(sync_health.get("tone") or "neutral")
    if sync_label == "error":
        return (
            "warning",
            {
                "tone": "bad",
                "summary": str(sync_health.get("summary") or "Recent sync work reported failures."),
                "detail": str(sync_health.get("detail") or ""),
            },
        )
    if sync_tone == "warn":
        sync_label = str(sync_health.get("label") or "")
        if sync_label == "needs_initial_sync":
            return (
                "needs_initial_sync",
                {
                    "tone": "warn",
                    "summary": str(sync_health.get("summary") or "Initial history sync has not run yet."),
                    "detail": str(sync_health.get("detail") or ""),
                },
            )
        return (
            "warning",
            {
                "tone": "warn",
                "summary": str(sync_health.get("summary") or "Recent sync work reported warnings."),
                "detail": str(sync_health.get("detail") or ""),
            },
        )
    return (
        "healthy",
        {
            "tone": "ok",
            "summary": "Live sync is active.",
            "detail": str(sync_health.get("summary") or ""),
        },
    )


def _tenant_backfill_status(*, enabled: bool, db_stats: dict[str, Any], sync_health: dict[str, Any]) -> dict[str, Any]:
    if not enabled:
        return {
            "label": "disabled",
            "tone": "neutral",
            "summary": "Backfill is idle while the tenant is disabled.",
            "detail": "Activate the tenant before running bounded backfill or reconcile work.",
        }
    embedding_pending = int(db_stats.get("embedding_pending") or 0)
    embedding_errors = int(db_stats.get("embedding_errors") or 0)
    derived_pending = int(db_stats.get("derived_pending") or 0)
    derived_errors = int(db_stats.get("derived_errors") or 0)
    reconcile = dict(sync_health.get("reconcile") or {})
    attempted = int(reconcile.get("attempted") or 0)
    downloaded = int(reconcile.get("downloaded") or 0)
    warnings = int(reconcile.get("warnings") or 0)
    failed = int(reconcile.get("failed") or 0)
    if embedding_errors or derived_errors or failed:
        return {
            "label": "error",
            "tone": "bad",
            "summary": f"Backfill queues or reconcile work have errors ({embedding_errors + derived_errors + failed}).",
            "detail": (
                f"reconcile downloaded={downloaded} warnings={warnings} failed={failed} · "
                f"embedding errors={embedding_errors} · derived-text errors={derived_errors}"
            ),
        }
    if embedding_pending or derived_pending:
        return {
            "label": "syncing",
            "tone": "warn",
            "summary": f"Initial history sync is in progress ({embedding_pending + derived_pending} pending jobs).",
            "detail": (
                f"embedding pending={embedding_pending} · derived-text pending={derived_pending} · "
                f"last reconcile attempted={attempted} downloaded={downloaded}"
            ),
        }
    if attempted or downloaded:
        return {
            "label": "current",
            "tone": "ok",
            "summary": "Backfill and reconcile state are current.",
            "detail": f"last reconcile attempted={attempted} downloaded={downloaded} warnings={warnings} failed={failed}",
        }
    return {
        "label": "needs_initial_sync",
        "tone": "warn",
        "summary": "Initial history sync has not run yet.",
        "detail": "Run initial sync to seed mirrored history and establish reconcile state for this tenant.",
    }


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
        live_units = _tenant_live_unit_states(ws_name)
        db_stats = _tenant_db_stats(resolved, ws_name)
        sync_health = _tenant_sync_health(config_path=resolved, name=ws_name, enabled=enabled)
        validation_status, health = _tenant_validation_status(
            enabled=enabled,
            credential_ready=credentials["ready"],
            db_synced=synced,
            live_units=live_units,
            sync_health=sync_health,
        )
        backfill_status = _tenant_backfill_status(enabled=enabled, db_stats=db_stats, sync_health=sync_health)
        next_action = "ready_to_activate"
        if enabled:
            live_states = {str(value or "unknown") for value in live_units.values()}
            if "active" not in live_states:
                next_action = "start_live_sync"
            elif str(backfill_status.get("label") or "") == "needs_initial_sync":
                next_action = "run_initial_sync"
            elif str(backfill_status.get("label") or "") in {"syncing", "error"}:
                next_action = "inspect_backfill_status"
            elif validation_status in {"warning", "needs_initial_sync"}:
                next_action = "inspect_sync_health"
            else:
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
                "validation_status": validation_status,
                "live_units": live_units,
                "db_stats": db_stats,
                "sync_health": sync_health,
                "backfill_status": backfill_status,
                "health": health,
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


def read_tenant_manifest(
    *,
    config_path: str | Path | None = None,
    name: str,
) -> dict[str, Any]:
    tenant_name = normalize_tenant_name(name)
    status = tenant_status(config_path=config_path, name=tenant_name)[0]
    manifest = status.get("manifest") or {}
    manifest_path = Path(str(manifest.get("path") or "")).expanduser()
    if not manifest_path.exists():
        raise FileNotFoundError(f"Rendered manifest not found for tenant '{tenant_name}': {manifest_path}")
    content = manifest_path.read_text(encoding="utf-8")
    json.loads(content)
    return {"tenant": status, "manifest_path": str(manifest_path), "content": content}


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
        backup = _backup_config(resolved, tenant_name=tenant_name, operation="onboard")
        _write_raw_config(resolved, raw)
        # Re-read through the normal loader so invalid YAML/env path issues are caught immediately.
        load_config(resolved)
        backup_path = str(backup)

    if sync_db and not dry_run:
        _sync_tenant_to_db(resolved, tenant_name)

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


def install_tenant_live_units(
    *,
    name: str,
    config_path: str | Path,
    runner: RunFn = subprocess.run,
) -> list[str]:
    tenant_name = normalize_tenant_name(name)
    script = _live_install_script()
    if not script.exists():
        raise FileNotFoundError(f"Live-mode installer script not found: {script}")
    command = [str(script), tenant_name, str(resolve_config_path(config_path))]
    _run_checked_command(
        command,
        runner=runner,
        failure_hint=(
            f"Live-sync install failed for tenant '{tenant_name}'. "
            f"Inspect `journalctl --user -u slack-mirror-webhooks-{tenant_name}.service "
            f"-u slack-mirror-daemon-{tenant_name}.service -n 50`"
        ),
    )
    return command


def activate_tenant(
    *,
    config_path: str | Path | None = None,
    name: str,
    dry_run: bool = False,
    install_live_units: bool = True,
    runner: RunFn = subprocess.run,
) -> TenantActivateResult:
    tenant_name = normalize_tenant_name(name)
    resolved = resolve_config_path(config_path)
    raw = _load_raw_config(resolved)
    existing = _find_workspace(raw, tenant_name)
    if existing is None:
        raise ValueError(f"Tenant '{tenant_name}' not found in config")

    before_status = tenant_status(config_path=resolved, name=tenant_name)[0]
    if not before_status.get("credential_ready"):
        missing = ", ".join(before_status.get("missing_required_credentials") or [])
        raise ValueError(f"Tenant '{tenant_name}' is missing required credentials: {missing}")

    was_enabled = bool(before_status.get("enabled"))
    changed = not was_enabled
    backup_path: str | None = None
    command: list[str] | None = None
    live_units_installed = False

    if changed and not dry_run:
        existing["enabled"] = True
        backup = _backup_config(resolved, tenant_name=tenant_name, operation="activate")
        _write_raw_config(resolved, raw)
        load_config(resolved)
        _sync_tenant_to_db(resolved, tenant_name)
        backup_path = str(backup)

    if not changed and not dry_run:
        _sync_tenant_to_db(resolved, tenant_name)

    if install_live_units:
        command = [str(_live_install_script()), tenant_name, str(resolved)]
        if not dry_run:
            command = install_tenant_live_units(name=tenant_name, config_path=resolved, runner=runner)
            live_units_installed = True

    status = tenant_status(config_path=resolved, name=tenant_name)[0]
    if dry_run and changed:
        status = {**status, "enabled": True, "next_action": "install_live_units" if install_live_units else "run_live_validation"}

    return TenantActivateResult(
        tenant=status,
        changed=changed,
        config_path=str(resolved),
        backup_path=backup_path,
        live_units_installed=live_units_installed,
        live_unit_command=command,
        dry_run=dry_run,
    )


def install_tenant_credentials(
    *,
    config_path: str | Path | None = None,
    name: str,
    credentials: dict[str, str],
    dry_run: bool = False,
) -> TenantCredentialInstallResult:
    tenant_name = normalize_tenant_name(name)
    resolved = resolve_config_path(config_path)
    raw = _load_raw_config(resolved)
    raw_ws = _find_workspace(raw, tenant_name)
    if raw_ws is None:
        raise ValueError(f"Tenant '{tenant_name}' not found in config")

    placeholders = tenant_credential_placeholders(tenant_name)
    accepted_by_field = {field: env_key for field, env_key in placeholders.items()}
    accepted_by_env = {env_key: field for field, env_key in placeholders.items()}
    dotenv_values: dict[str, str] = {}
    skipped: list[str] = []
    for key, value in credentials.items():
        raw_key = str(key or "").strip()
        raw_value = str(value or "").strip()
        if not raw_key or not raw_value:
            skipped.append(raw_key)
            continue
        field = raw_key if raw_key in accepted_by_field else accepted_by_env.get(raw_key)
        if field is None:
            skipped.append(raw_key)
            continue
        dotenv_values[accepted_by_field[field]] = raw_value
    if not dotenv_values:
        raise ValueError(f"No recognized credentials provided for tenant '{tenant_name}'")

    dotenv_path = _dotenv_path_for_config(raw, resolved)
    backup = None if dry_run else _backup_dotenv(dotenv_path, tenant_name=tenant_name)
    changed = _upsert_dotenv_values(dotenv_path, dotenv_values, dry_run=dry_run)

    original_env = {key: os.environ.get(key) for key in dotenv_values}
    try:
        for key, value in dotenv_values.items():
            os.environ[key] = value
        status = tenant_status(config_path=resolved, name=tenant_name)[0]
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    return TenantCredentialInstallResult(
        tenant=status,
        changed=changed,
        dotenv_path=str(dotenv_path),
        backup_path=str(backup) if backup else None,
        installed_keys=sorted(dotenv_values),
        skipped_keys=sorted(item for item in skipped if item),
        dry_run=dry_run,
    )


def manage_tenant_live_units(
    *,
    config_path: str | Path | None = None,
    name: str,
    action: str,
    dry_run: bool = False,
    runner: RunFn = subprocess.run,
) -> TenantCommandResult:
    tenant_name = normalize_tenant_name(name)
    resolved = resolve_config_path(config_path)
    tenant = tenant_status(config_path=resolved, name=tenant_name)[0]
    if action == "start":
        command = [str(_live_install_script()), tenant_name, str(resolved)]
        commands = [command]
        if not dry_run:
            install_tenant_live_units(name=tenant_name, config_path=resolved, runner=runner)
    elif action in {"restart", "stop"}:
        command = _systemctl_user_command(action, tenant_name)
        commands = [command]
        if not dry_run:
            _run_checked_command(
                command,
                runner=runner,
                failure_hint=(
                    f"Live-sync action '{action}' failed for tenant '{tenant_name}'. "
                    f"Inspect `journalctl --user -u slack-mirror-webhooks-{tenant_name}.service "
                    f"-u slack-mirror-daemon-{tenant_name}.service -n 50`"
                ),
            )
    else:
        raise ValueError("live action must be one of: start, restart, stop")
    return TenantCommandResult(tenant=tenant, action=action, commands=commands, dry_run=dry_run)


def run_tenant_backfill(
    *,
    config_path: str | Path | None = None,
    name: str,
    auth_mode: str = "user",
    include_messages: bool = True,
    include_files: bool = False,
    channel_limit: int = 10,
    dry_run: bool = False,
    runner: RunFn = subprocess.run,
) -> TenantCommandResult:
    tenant_name = normalize_tenant_name(name)
    resolved = resolve_config_path(config_path)
    tenant = tenant_status(config_path=resolved, name=tenant_name)[0]
    if not dry_run and not tenant.get("enabled"):
        raise ValueError(f"Tenant '{tenant_name}' must be enabled before backfill")
    if auth_mode not in {"bot", "user"}:
        raise ValueError("auth_mode must be 'bot' or 'user'")
    if channel_limit < 1 or channel_limit > 1000:
        raise ValueError("channel_limit must be between 1 and 1000")
    command = [
        *_slack_mirror_command(resolved),
        "mirror",
        "backfill",
        "--workspace",
        tenant_name,
        "--auth-mode",
        auth_mode,
        "--channel-limit",
        str(channel_limit),
    ]
    if include_messages:
        command.append("--include-messages")
    if include_files:
        command.append("--include-files")
    if not include_messages and not include_files:
        # Users/channels bootstrap only.
        pass
    if not dry_run:
        runner(command, check=True)
    return TenantCommandResult(tenant=tenant, action="backfill", commands=[command], dry_run=dry_run)


def retire_tenant(
    *,
    config_path: str | Path | None = None,
    name: str,
    delete_db: bool = False,
    stop_live_units: bool = True,
    dry_run: bool = False,
    runner: RunFn = subprocess.run,
) -> TenantRetireResult:
    tenant_name = normalize_tenant_name(name)
    resolved = resolve_config_path(config_path)
    raw = _load_raw_config(resolved)
    workspaces = raw.get("workspaces") or []
    if not isinstance(workspaces, list):
        raise ValueError("config workspaces must be a list")
    existing = _find_workspace(raw, tenant_name)
    if existing is None:
        raise ValueError(f"Tenant '{tenant_name}' not found in config")
    if tenant_name in {"default", "soylei"}:
        raise ValueError(f"Tenant '{tenant_name}' is protected from browser retirement")

    before_status = tenant_status(config_path=resolved, name=tenant_name)[0]
    live_commands: list[list[str]] = []
    if stop_live_units:
        live_commands.append(_systemctl_user_command("stop", tenant_name))

    db_deleted = False
    db_counts: dict[str, int] = {}
    if delete_db:
        db_deleted, db_counts = _delete_tenant_db_rows(resolved, tenant_name, dry_run=True)

    backup_path: str | None = None
    if not dry_run:
        if stop_live_units:
            for command in live_commands:
                runner(command, check=False)
        if delete_db:
            db_deleted, db_counts = _delete_tenant_db_rows(resolved, tenant_name, dry_run=False)
        raw["workspaces"] = [
            item for item in workspaces if not (isinstance(item, dict) and item.get("name") == tenant_name)
        ]
        backup = _backup_config(resolved, tenant_name=tenant_name, operation="retire")
        _write_raw_config(resolved, raw)
        load_config(resolved)
        backup_path = str(backup)

    return TenantRetireResult(
        tenant=before_status,
        changed=True,
        config_path=str(resolved),
        backup_path=backup_path,
        db_deleted=db_deleted,
        db_counts=db_counts,
        live_unit_commands=live_commands,
        dry_run=dry_run,
    )
