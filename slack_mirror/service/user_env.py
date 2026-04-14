from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from slack_mirror.core.config import load_config
from slack_mirror.service.runtime_heartbeat import heartbeat_path_for_config, load_reconcile_state


RunFn = Callable[..., subprocess.CompletedProcess]
PrintFn = Callable[[str], None]

LIVE_EVENT_PENDING_FAIL_THRESHOLD = 100
LIVE_EMBEDDING_PENDING_FAIL_THRESHOLD = 1000
LIVE_STALE_HOURS = 24.0
LIVE_DAEMON_HEARTBEAT_STALE_SECONDS = 10 * 60


def _config_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class UserEnvPaths:
    repo_root: Path
    home_dir: Path
    app_root: Path
    app_dir: Path
    backup_app_dir: Path
    venv_dir: Path
    legacy_state_dir: Path
    state_dir: Path
    cache_dir: Path
    config_dir: Path
    bin_dir: Path
    config_path: Path
    env_path: Path
    wrapper_path: Path
    api_wrapper_path: Path
    mcp_wrapper_path: Path
    api_service_path: Path
    snapshot_service_path: Path
    snapshot_timer_path: Path


@dataclass(frozen=True)
class LiveValidationIssue:
    severity: str
    code: str
    message: str
    action: str | None = None
    workspace: str | None = None


@dataclass(frozen=True)
class LiveValidationWorkspace:
    name: str
    event_errors: int
    embedding_errors: int
    event_pending: int
    embedding_pending: int
    daemon_heartbeat_age_seconds: float | None
    active_recent_channels: int
    shell_like_zero_message_channels: int
    unexpected_empty_channels: int
    stale_channels: int
    stale_warning_suppressed: bool
    reconcile_state_present: bool
    reconcile_state_age_seconds: float | None
    reconcile_auth_mode: str | None
    reconcile_iso_utc: str | None
    reconcile_attempted: int
    reconcile_downloaded: int
    reconcile_warnings: int
    reconcile_failed: int
    failure_codes: list[str]
    warning_codes: list[str]


@dataclass(frozen=True)
class LiveValidationReport:
    ok: bool
    status: str
    require_live_units: bool
    exit_code: int
    summary: str
    failure_count: int
    warning_count: int
    failure_codes: list[str]
    warning_codes: list[str]
    failures: list[LiveValidationIssue]
    warnings: list[LiveValidationIssue]
    workspaces: list[LiveValidationWorkspace]


@dataclass(frozen=True)
class UserEnvStatusReport:
    wrapper_present: bool
    api_wrapper_present: bool
    mcp_wrapper_present: bool
    api_service_present: bool
    rollback_snapshot_present: bool
    config_present: bool
    db_present: bool
    cache_present: bool
    services: dict[str, str]
    reconcile_workspaces: list[dict[str, Any]]


@dataclass(frozen=True)
class LiveSmokeCheckReport:
    ok: bool
    status: str
    exit_code: int
    summary: str
    failure_count: int
    warning_count: int
    failure_codes: list[str]
    warning_codes: list[str]
    failures: list[LiveValidationIssue]
    warnings: list[LiveValidationIssue]
    status_report: UserEnvStatusReport
    validation_report: LiveValidationReport


@dataclass(frozen=True)
class LiveRecoveryAction:
    code: str
    description: str
    command: list[str] | None
    safe: bool
    workspace: str | None = None


@dataclass(frozen=True)
class LiveRecoveryReport:
    ok: bool
    status: str
    exit_code: int
    applied: bool
    summary: str
    actionable_count: int
    operator_only_count: int
    action_codes: list[str]
    operator_only_codes: list[str]
    actions: list[LiveRecoveryAction]
    operator_only_issues: list[LiveValidationIssue]
    smoke_report: LiveSmokeCheckReport


def default_user_env_paths(
    *,
    repo_root: Path | None = None,
    home: Path | None = None,
    xdg_state_home: Path | None = None,
    xdg_cache_home: Path | None = None,
) -> UserEnvPaths:
    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    user_home = (home or Path.home()).expanduser().resolve()
    state_home = (xdg_state_home or Path(os.environ.get("XDG_STATE_HOME", user_home / ".local" / "state"))).expanduser()
    cache_home = (xdg_cache_home or Path(os.environ.get("XDG_CACHE_HOME", user_home / ".local" / "cache"))).expanduser()
    app_root = user_home / ".local" / "share" / "slack-mirror"
    config_dir = user_home / ".config" / "slack-mirror"
    bin_dir = user_home / ".local" / "bin"
    state_dir = state_home / "slack-mirror"
    cache_dir = cache_home / "slack-mirror"
    return UserEnvPaths(
        repo_root=root,
        home_dir=user_home,
        app_root=app_root,
        app_dir=app_root / "app",
        backup_app_dir=app_root / "app.previous",
        venv_dir=app_root / "venv",
        legacy_state_dir=app_root / "var",
        state_dir=state_dir,
        cache_dir=cache_dir,
        config_dir=config_dir,
        bin_dir=bin_dir,
        config_path=config_dir / "config.yaml",
        env_path=config_dir / "env.sh",
        wrapper_path=bin_dir / "slack-mirror-user",
        api_wrapper_path=bin_dir / "slack-mirror-api",
        mcp_wrapper_path=bin_dir / "slack-mirror-mcp",
        api_service_path=user_home / ".config" / "systemd" / "user" / "slack-mirror-api.service",
        snapshot_service_path=user_home / ".config" / "systemd" / "user" / "slack-mirror-runtime-report.service",
        snapshot_timer_path=user_home / ".config" / "systemd" / "user" / "slack-mirror-runtime-report.timer",
    )


def _log(out: PrintFn, message: str) -> None:
    out(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")


def _run(
    runner: RunFn,
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    completed = runner(args, check=False, text=True, env=env, capture_output=capture_output)
    if int(completed.returncode) != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(args)}")
    return completed


def _runtime_env(paths: UserEnvPaths) -> dict[str, str]:
    env = os.environ.copy()
    env["SLACK_MIRROR_DB"] = str(paths.state_dir / "slack_mirror.db")
    env["SLACK_MIRROR_CACHE"] = str(paths.cache_dir)
    return env


def _load_managed_config(paths: UserEnvPaths) -> Any:
    original_db = os.environ.get("SLACK_MIRROR_DB")
    original_cache = os.environ.get("SLACK_MIRROR_CACHE")
    runtime_env = _runtime_env(paths)
    try:
        os.environ["SLACK_MIRROR_DB"] = runtime_env["SLACK_MIRROR_DB"]
        os.environ["SLACK_MIRROR_CACHE"] = runtime_env["SLACK_MIRROR_CACHE"]
        return load_config(paths.config_path)
    finally:
        if original_db is None:
            os.environ.pop("SLACK_MIRROR_DB", None)
        else:
            os.environ["SLACK_MIRROR_DB"] = original_db
        if original_cache is None:
            os.environ.pop("SLACK_MIRROR_CACHE", None)
        else:
            os.environ["SLACK_MIRROR_CACHE"] = original_cache


def _ensure_dirs(paths: UserEnvPaths) -> None:
    for path in (paths.bin_dir, paths.config_dir, paths.state_dir, paths.cache_dir):
        path.mkdir(parents=True, exist_ok=True)


def _write_env_file(paths: UserEnvPaths) -> None:
    paths.env_path.write_text(
        "# Generated by slack-mirror user-env\n"
        f'export SLACK_MIRROR_DB="{paths.state_dir / "slack_mirror.db"}"\n'
        f'export SLACK_MIRROR_CACHE="{paths.cache_dir}"\n',
        encoding="utf-8",
    )


def _ignore_repo_snapshot(_dir: str, names: list[str]) -> set[str]:
    ignored = {".git", ".venv", ".pytest_cache", "__pycache__", "cache", ".openclaw"}
    ignored.update(name for name in names if name.startswith("localhost+") and name.endswith(".pem"))
    return ignored.intersection(names)


def _copy_repo_snapshot(paths: UserEnvPaths) -> None:
    if paths.app_dir.exists():
        shutil.rmtree(paths.app_dir)
    shutil.copytree(paths.repo_root, paths.app_dir, ignore=_ignore_repo_snapshot)


def _rotate_app_snapshot_backup(paths: UserEnvPaths, *, out: PrintFn) -> None:
    if paths.backup_app_dir.exists():
        shutil.rmtree(paths.backup_app_dir)
    if paths.app_dir.exists():
        _log(out, f"saving previous app snapshot: {paths.backup_app_dir}")
        shutil.move(str(paths.app_dir), str(paths.backup_app_dir))


def _swap_app_snapshot_with_backup(paths: UserEnvPaths, *, out: PrintFn) -> None:
    if not paths.backup_app_dir.exists():
        raise FileNotFoundError(f"rollback snapshot missing: {paths.backup_app_dir}")

    swap_dir = paths.app_root / "app.swap"
    if swap_dir.exists():
        shutil.rmtree(swap_dir)

    current_exists = paths.app_dir.exists()
    if current_exists:
        _log(out, f"parking current app snapshot: {swap_dir}")
        shutil.move(str(paths.app_dir), str(swap_dir))

    _log(out, f"restoring rollback snapshot: {paths.backup_app_dir}")
    shutil.move(str(paths.backup_app_dir), str(paths.app_dir))

    if current_exists:
        shutil.move(str(swap_dir), str(paths.backup_app_dir))


def _ensure_venv(
    paths: UserEnvPaths,
    *,
    runner: RunFn,
    python_executable: str | None = None,
    out: PrintFn,
) -> None:
    venv_python = paths.venv_dir / "bin" / "python"
    if not venv_python.exists():
        python = python_executable or sys.executable or "python3"
        _log(out, f"creating venv: {paths.venv_dir}")
        _run(runner, [python, "-m", "venv", str(paths.venv_dir)])
    _run(runner, [str(paths.venv_dir / "bin" / "pip"), "install", "--upgrade", "pip", "wheel", "setuptools"])


def _install_python_package(paths: UserEnvPaths, *, runner: RunFn, out: PrintFn) -> None:
    _log(out, "installing package into venv")
    _run(runner, [str(paths.venv_dir / "bin" / "pip"), "install", "--upgrade", str(paths.app_dir)])


def _ensure_config(paths: UserEnvPaths, *, out: PrintFn) -> None:
    template = paths.app_dir / "config.example.yaml"
    if not template.exists():
        raise FileNotFoundError(f"config template missing from app snapshot: {template}")
    if not paths.config_path.exists():
        _log(out, f"creating config from template: {paths.config_path}")
        shutil.copy2(template, paths.config_path)
    shutil.copy2(template, paths.config_dir / "config.example.latest.yaml")


def _migrate_legacy_state(paths: UserEnvPaths, *, out: PrintFn) -> None:
    legacy_db = paths.legacy_state_dir / "slack_mirror.db"
    target_db = paths.state_dir / "slack_mirror.db"
    legacy_cache = paths.legacy_state_dir / "cache"

    if not target_db.exists() and legacy_db.exists():
        _log(out, f"migrating legacy DB into stable state dir: {target_db}")
        shutil.copy2(legacy_db, target_db)

    cache_empty = not paths.cache_dir.exists() or not any(paths.cache_dir.iterdir())
    if cache_empty and legacy_cache.exists():
        _log(out, f"migrating legacy cache into stable cache dir: {paths.cache_dir}")
        paths.cache_dir.mkdir(parents=True, exist_ok=True)
        for item in legacy_cache.iterdir():
            dst = paths.cache_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)


def _command_args(args: list[str]) -> str:
    return " ".join(f'"{arg}"' for arg in args)


def _write_wrapper(paths: UserEnvPaths, *, args: list[str], target_path: Path) -> None:
    command = _command_args(args)
    command_part = f" {command}" if command else ""
    content = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'source "{paths.env_path}"\n'
        f'exec "{paths.venv_dir / "bin" / "slack-mirror"}" --config "{paths.config_path}"{command_part} "$@"\n'
    )
    target_path.write_text(content, encoding="utf-8")
    target_path.chmod(0o755)


def _write_wrappers(paths: UserEnvPaths) -> None:
    _write_wrapper(paths, args=[], target_path=paths.wrapper_path)
    _write_wrapper(paths, args=["api", "serve"], target_path=paths.api_wrapper_path)
    _write_wrapper(paths, args=["mcp", "serve"], target_path=paths.mcp_wrapper_path)


def _write_api_service(paths: UserEnvPaths) -> None:
    content = (
        "[Unit]\n"
        "Description=Slack Mirror API Service\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={paths.api_wrapper_path}\n"
        "Restart=always\n"
        "RestartSec=2\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
    paths.api_service_path.write_text(content, encoding="utf-8")


def _write_snapshot_report_units(paths: UserEnvPaths) -> None:
    service_content = (
        "[Unit]\n"
        "Description=Slack Mirror Runtime Report Snapshot\n"
        "After=network-online.target slack-mirror-api.service\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={paths.wrapper_path} user-env snapshot-report --name scheduled-runtime-report\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    timer_content = (
        "[Unit]\n"
        "Description=Slack Mirror Runtime Report Snapshot Timer\n"
        "\n"
        "[Timer]\n"
        "OnBootSec=5m\n"
        "OnUnitActiveSec=1h\n"
        "Persistent=true\n"
        "Unit=slack-mirror-runtime-report.service\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )
    paths.snapshot_service_path.parent.mkdir(parents=True, exist_ok=True)
    paths.snapshot_service_path.write_text(service_content, encoding="utf-8")
    paths.snapshot_timer_path.write_text(timer_content, encoding="utf-8")


def _user_unit_path(paths: UserEnvPaths, unit_name: str) -> Path:
    return paths.home_dir / ".config" / "systemd" / "user" / unit_name


def _systemctl_state(runner: RunFn, unit_name: str) -> str:
    completed = runner(
        ["systemctl", "--user", "is-active", unit_name],
        check=False,
        text=True,
        capture_output=True,
    )
    state = (completed.stdout or "").strip()
    if state:
        return state
    if completed.returncode != 0:
        return "inactive"
    return "unknown"


def _db_status_counts(db_path: Path, workspace: str, table: str) -> dict[str, int]:
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        rows = conn.execute(
            f"""
            SELECT t.status, COUNT(*)
            FROM {table} t
            JOIN workspaces w ON w.id = t.workspace_id
            WHERE w.name = ?
            GROUP BY t.status
            ORDER BY t.status
            """,
            (workspace,),
        )
        return {str(status): int(count) for status, count in rows}
    finally:
        conn.close()


def _db_workspace_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        rows = conn.execute("SELECT name FROM workspaces ORDER BY name")
        return {str(name) for (name,) in rows}
    finally:
        conn.close()


def _db_workspace_stale_channels(db_path: Path, workspace: str, *, stale_hours: float) -> int:
    stale_cutoff_ts = time.time() - (float(stale_hours) * 3600.0)
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        row = conn.execute(
            """
            WITH last_msg AS (
              SELECT workspace_id, channel_id, max(cast(ts as real)) AS max_ts
              FROM messages
              GROUP BY workspace_id, channel_id
            )
            SELECT sum(case when lm.max_ts is not null and lm.max_ts < ? then 1 else 0 end) AS stale_channels
            FROM channels c
            JOIN workspaces w ON w.id = c.workspace_id
            LEFT JOIN last_msg lm ON lm.workspace_id = c.workspace_id AND lm.channel_id = c.channel_id
            WHERE w.name = ?
            """,
            (stale_cutoff_ts, workspace),
        ).fetchone()
        return int((row[0] if row and row[0] is not None else 0))
    finally:
        conn.close()


def _db_workspace_access_summary(db_path: Path, workspace: str, *, stale_hours: float) -> dict[str, int]:
    stale_cutoff_ts = time.time() - (float(stale_hours) * 3600.0)
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        row = conn.execute(
            """
            WITH last_msg AS (
              SELECT workspace_id, channel_id, max(cast(ts as real)) AS max_ts, count(*) AS msg_count
              FROM messages
              GROUP BY workspace_id, channel_id
            )
            SELECT
              sum(case when coalesce(lm.msg_count,0)>0 and lm.max_ts >= ? then 1 else 0 end) as active_recent_channels,
              sum(case when coalesce(lm.msg_count,0)=0 and (c.is_im=1 or c.is_mpim=1) then 1 else 0 end) as shell_like_zero_message_channels,
              sum(case when coalesce(lm.msg_count,0)=0 and c.is_im=0 and c.is_mpim=0 then 1 else 0 end) as unexpected_empty_channels
            FROM channels c
            JOIN workspaces w ON w.id = c.workspace_id
            LEFT JOIN last_msg lm ON lm.workspace_id = c.workspace_id AND lm.channel_id = c.channel_id
            WHERE w.name = ?
            """,
            (stale_cutoff_ts, workspace),
        ).fetchone()
        return {
            "active_recent_channels": int((row[0] if row and row[0] is not None else 0)),
            "shell_like_zero_message_channels": int((row[1] if row and row[1] is not None else 0)),
            "unexpected_empty_channels": int((row[2] if row and row[2] is not None else 0)),
        }
    finally:
        conn.close()


def _heartbeat_age_seconds(config_path: Path, workspace: str, *, kind: str) -> float | None:
    path = heartbeat_path_for_config(str(config_path), workspace=workspace, kind=kind)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        ts = float(payload.get("ts"))
    except (TypeError, ValueError):
        return None
    age = time.time() - ts
    return max(age, 0.0)


def _build_live_validation_report(
    *,
    paths: UserEnvPaths | None = None,
    runner: RunFn = subprocess.run,
    require_live_units: bool = True,
) -> LiveValidationReport:
    target = paths or default_user_env_paths()
    failures: list[LiveValidationIssue] = []
    warnings: list[LiveValidationIssue] = []
    workspace_reports: list[LiveValidationWorkspace] = []

    def fail(code: str, message: str, action: str | None = None, *, workspace: str | None = None) -> None:
        failures.append(LiveValidationIssue("fail", code, message, action=action, workspace=workspace))

    def warn(code: str, message: str, action: str | None = None, *, workspace: str | None = None) -> None:
        warnings.append(LiveValidationIssue("warn", code, message, action=action, workspace=workspace))

    if not target.config_path.exists():
        fail(
            "CONFIG_MISSING",
            "managed config is missing",
            "run `slack-mirror user-env install` or restore ~/.config/slack-mirror/config.yaml",
        )
        return _finalize_live_validation_report(
            failures=failures,
            warnings=warnings,
            require_live_units=require_live_units,
            workspaces=workspace_reports,
        )

    try:
        cfg = _load_managed_config(target)
    except Exception as exc:
        fail(
            "CONFIG_INVALID",
            f"managed config could not be loaded: {exc}",
            "fix the config or dotenv path, then rerun `slack-mirror user-env validate-live`",
        )
        return _finalize_live_validation_report(
            failures=failures,
            warnings=warnings,
            require_live_units=require_live_units,
            workspaces=workspace_reports,
        )

    db_path = Path(str(cfg.get("storage", {}).get("db_path", target.state_dir / "slack_mirror.db"))).expanduser()
    auth_cfg = (cfg.get("service", {}) or {}).get("auth", {}) or {}
    auth_enabled = _config_bool(auth_cfg.get("enabled"), False)
    auth_allow_registration = _config_bool(auth_cfg.get("allow_registration"), True)
    auth_registration_allowlist = auth_cfg.get("registration_allowlist") or []
    external_base_url = str((cfg.get("exports", {}) or {}).get("external_base_url") or "").strip()
    if not db_path.exists():
        fail(
            "DB_MISSING",
            "managed DB is missing",
            "run `slack-mirror user-env install` or `slack-mirror-user mirror init && slack-mirror-user workspaces sync-config`",
        )
        return _finalize_live_validation_report(
            failures=failures,
            warnings=warnings,
            require_live_units=require_live_units,
            workspaces=workspace_reports,
        )

    workspace_configs = [ws for ws in cfg.get("workspaces", []) if ws.get("name") and ws.get("enabled", True)]
    if not workspace_configs:
        fail(
            "WORKSPACE_CONFIG",
            "no enabled workspaces found in managed config",
            "add at least one enabled workspace to config.yaml and rerun workspace sync",
        )
        return _finalize_live_validation_report(
            failures=failures,
            warnings=warnings,
            require_live_units=require_live_units,
            workspaces=workspace_reports,
        )

    api_unit = "slack-mirror-api.service"
    if not target.api_service_path.exists():
        fail(
            "API_UNIT_MISSING",
            f"{api_unit} unit file missing",
            "run `slack-mirror user-env update` to recreate the managed API service",
        )
    api_state = _systemctl_state(runner, api_unit)
    if api_state != "active":
        fail(
            "API_UNIT_INACTIVE",
            f"{api_unit} state={api_state}",
            f"run `systemctl --user restart {api_unit}` and inspect `journalctl --user -u {api_unit} -n 50`",
        )

    if auth_enabled and auth_allow_registration and external_base_url:
        allowlisted = bool(auth_registration_allowlist)
        registration_mode = "allowlisted" if allowlisted else "open"
        warn(
            "AUTH_REGISTRATION_EXTERNAL",
            (
                f"frontend auth self-registration is {registration_mode} while external publishing is configured "
                f"({external_base_url})"
            ),
            "disable `service.auth.allow_registration` after initial bootstrap unless ongoing browser self-registration is intentional",
        )

    try:
        db_workspaces = _db_workspace_names(db_path)
    except sqlite3.DatabaseError as exc:
        fail(
            "DB_UNREADABLE",
            f"managed DB unreadable: {exc}",
            "inspect the DB path in config, then rerun `slack-mirror-user mirror init` if schema repair is needed",
        )
        return _finalize_live_validation_report(
            failures=failures,
            warnings=warnings,
            require_live_units=require_live_units,
            workspaces=workspace_reports,
        )

    for ws in workspace_configs:
        name = str(ws.get("name"))
        ws_failures: list[str] = []
        ws_warnings: list[str] = []

        def ws_fail(code: str, message: str, action: str | None = None) -> None:
            ws_failures.append(code)
            fail(code, message, action, workspace=name)

        def ws_warn(code: str, message: str, action: str | None = None) -> None:
            ws_warnings.append(code)
            warn(code, message, action, workspace=name)

        if name not in db_workspaces:
            ws_fail(
                "WORKSPACE_DB_MISSING",
                f"workspace {name} missing from DB",
                f"run `slack-mirror-user workspaces sync-config` for workspace `{name}`",
            )

        outbound_token = ws.get("outbound_token") or ws.get("write_token")
        outbound_user_token = ws.get("outbound_user_token") or ws.get("write_user_token")
        if not outbound_token:
            ws_fail(
                "OUTBOUND_TOKEN_MISSING",
                f"workspace {name} missing explicit outbound bot token",
                f"set `outbound_token` or `write_token` for workspace `{name}`",
            )
        if ws.get("user_token") and not outbound_user_token:
            ws_fail(
                "OUTBOUND_USER_TOKEN_MISSING",
                f"workspace {name} missing explicit outbound user token",
                f"set `outbound_user_token` or `write_user_token` for workspace `{name}`",
            )

        receiver_unit = f"slack-mirror-webhooks-{name}.service"
        daemon_unit = f"slack-mirror-daemon-{name}.service"
        if require_live_units:
            for unit_name in (receiver_unit, daemon_unit):
                unit_path = _user_unit_path(target, unit_name)
                if not unit_path.exists():
                    ws_fail(
                        "LIVE_UNIT_MISSING",
                        f"{unit_name} unit file missing",
                        f"run `scripts/install_live_mode_systemd_user.sh {name}` or reinstall the managed live stack",
                    )
                unit_state = _systemctl_state(runner, unit_name)
                if unit_state != "active":
                    ws_fail(
                        "LIVE_UNIT_INACTIVE",
                        f"{unit_name} state={unit_state}",
                        f"run `systemctl --user restart {receiver_unit} {daemon_unit}` and inspect `journalctl --user -u {receiver_unit} -u {daemon_unit} -n 50`",
                    )

            for unit_name in (
                f"slack-mirror-events-{name}.service",
                f"slack-mirror-embeddings-{name}.service",
            ):
                if _systemctl_state(runner, unit_name) == "active":
                    ws_fail(
                        "DUPLICATE_TOPOLOGY",
                        f"duplicate topology active: {unit_name}",
                        f"run `systemctl --user disable --now {unit_name}` to keep only the unified daemon topology for `{name}`",
                    )

            daemon_heartbeat_age = _heartbeat_age_seconds(target.config_path, name, kind="daemon")
            if daemon_heartbeat_age is None:
                ws_fail(
                    "DAEMON_HEARTBEAT_MISSING",
                    f"workspace {name} has no recent daemon heartbeat record",
                    f"run `systemctl --user restart {daemon_unit}` and confirm `{daemon_unit}` is writing heartbeat state under the managed DB directory",
                )
            elif daemon_heartbeat_age > LIVE_DAEMON_HEARTBEAT_STALE_SECONDS:
                ws_fail(
                    "DAEMON_HEARTBEAT_STALE",
                    (
                        f"workspace {name} daemon heartbeat is stale at {int(daemon_heartbeat_age)}s "
                        f"(threshold {LIVE_DAEMON_HEARTBEAT_STALE_SECONDS}s)"
                    ),
                    f"run `systemctl --user restart {daemon_unit}` and inspect `journalctl --user -u {daemon_unit} -n 50`",
                )
        else:
            daemon_heartbeat_age = None

        try:
            event_counts = _db_status_counts(db_path, name, "events")
            embedding_counts = _db_status_counts(db_path, name, "embedding_jobs")
        except sqlite3.DatabaseError as exc:
            ws_fail(
                "QUEUE_INSPECTION_FAILED",
                f"workspace {name} queue inspection failed: {exc}",
                f"inspect `{db_path}` and rerun `slack-mirror user-env validate-live` after DB health is restored",
            )
            workspace_reports.append(
                LiveValidationWorkspace(
                    name=name,
                    event_errors=0,
                    embedding_errors=0,
                    event_pending=0,
                    embedding_pending=0,
                    daemon_heartbeat_age_seconds=daemon_heartbeat_age,
                    active_recent_channels=0,
                    shell_like_zero_message_channels=0,
                    unexpected_empty_channels=0,
                    stale_channels=0,
                    stale_warning_suppressed=False,
                    reconcile_state_present=False,
                    reconcile_state_age_seconds=None,
                    reconcile_auth_mode=None,
                    reconcile_iso_utc=None,
                    reconcile_attempted=0,
                    reconcile_downloaded=0,
                    reconcile_warnings=0,
                    reconcile_failed=0,
                    failure_codes=ws_failures,
                    warning_codes=ws_warnings,
                )
            )
            continue

        event_errors = event_counts.get("error", 0)
        embedding_errors = embedding_counts.get("error", 0)
        event_pending = event_counts.get("pending", 0)
        embedding_pending = embedding_counts.get("pending", 0)
        try:
            stale_channels = _db_workspace_stale_channels(db_path, name, stale_hours=LIVE_STALE_HOURS)
            access_summary = _db_workspace_access_summary(db_path, name, stale_hours=LIVE_STALE_HOURS)
        except sqlite3.DatabaseError as exc:
            ws_fail(
                "FRESHNESS_INSPECTION_FAILED",
                f"workspace {name} freshness inspection failed: {exc}",
                f"inspect `{db_path}` and rerun `slack-mirror user-env validate-live` after DB health is restored",
            )
            stale_channels = 0
            access_summary = {
                "active_recent_channels": 0,
                "shell_like_zero_message_channels": 0,
                "unexpected_empty_channels": 0,
            }

        reconcile_state = load_reconcile_state(target.config_path, workspace=name, auth_mode="user")
        reconcile_state_present = reconcile_state is not None
        reconcile_state_age_seconds: float | None = None
        reconcile_iso_utc: str | None = None
        reconcile_attempted = 0
        reconcile_downloaded = 0
        reconcile_warnings = 0
        reconcile_failed = 0
        if reconcile_state:
            reconcile_ts = reconcile_state.get("ts")
            if reconcile_ts is not None:
                try:
                    reconcile_state_age_seconds = max(0.0, time.time() - float(reconcile_ts))
                except (TypeError, ValueError):
                    reconcile_state_age_seconds = None
            reconcile_iso_utc = str(reconcile_state.get("iso_utc") or "") or None
            reconcile_attempted = int(reconcile_state.get("attempted") or 0)
            reconcile_downloaded = int(reconcile_state.get("downloaded") or 0)
            reconcile_warnings = int(reconcile_state.get("warnings") or 0)
            reconcile_failed = int(reconcile_state.get("failed") or 0)
            if reconcile_failed:
                ws_warn(
                    "RECONCILE_REPAIR_FAILURES",
                    f"workspace {name} last reconcile-files run had {reconcile_failed} failures",
                    (
                        f"inspect `{target.state_dir / 'reconcile-state' / f'reconcile-files-{name}-user.json'}` "
                        f"or rerun `slack-mirror --config {target.config_path} mirror reconcile-files --workspace {name} --auth-mode user --json`"
                    ),
                )
            elif reconcile_warnings:
                ws_warn(
                    "RECONCILE_REPAIR_WARNINGS",
                    f"workspace {name} last reconcile-files run had {reconcile_warnings} warnings",
                    (
                        f"inspect `{target.state_dir / 'reconcile-state' / f'reconcile-files-{name}-user.json'}` "
                        f"or rerun `slack-mirror --config {target.config_path} mirror reconcile-files --workspace {name} --auth-mode user --json`"
                    ),
                )

        if event_errors:
            handler = ws_fail if require_live_units else ws_warn
            handler(
                "EVENT_ERRORS",
                f"workspace {name} has event errors: {event_errors}",
                f"inspect `journalctl --user -u {receiver_unit} -u {daemon_unit} -n 50` and replay or clear failed event rows if needed",
            )
        if embedding_errors:
            handler = ws_fail if require_live_units else ws_warn
            handler(
                "EMBEDDING_ERRORS",
                f"workspace {name} has embedding job errors: {embedding_errors}",
                f"inspect daemon logs and replay or clear failed embedding jobs for workspace `{name}`",
            )

        if require_live_units and event_pending > LIVE_EVENT_PENDING_FAIL_THRESHOLD:
            ws_fail(
                "EVENT_BACKLOG",
                f"workspace {name} pending event backlog is {event_pending} (threshold {LIVE_EVENT_PENDING_FAIL_THRESHOLD})",
                f"inspect `journalctl --user -u {receiver_unit} -u {daemon_unit} -n 50` and confirm the daemon is draining events for `{name}`",
            )
        elif event_pending:
            ws_warn(
                "EVENT_PENDING",
                f"workspace {name} has pending events: {event_pending}",
                f"watch the queue and rerun `slack-mirror user-env validate-live` if it does not drain for `{name}`",
            )

        if require_live_units and embedding_pending > LIVE_EMBEDDING_PENDING_FAIL_THRESHOLD:
            ws_fail(
                "EMBEDDING_BACKLOG",
                f"workspace {name} pending embedding backlog is {embedding_pending} (threshold {LIVE_EMBEDDING_PENDING_FAIL_THRESHOLD})",
                f"inspect daemon logs and embedding throughput for workspace `{name}`",
            )
        elif embedding_pending:
            ws_warn(
                "EMBEDDING_PENDING",
                f"workspace {name} has pending embedding jobs: {embedding_pending}",
                f"watch embedding queue drain and rerun validation if backlog persists for `{name}`",
            )

        stale_warning_suppressed = False
        if stale_channels:
            if require_live_units and access_summary["active_recent_channels"] > 0 and access_summary["unexpected_empty_channels"] == 0:
                stale_warning_suppressed = True
            else:
                ws_warn(
                    "STALE_MIRROR",
                    f"workspace {name} has {stale_channels} stale mirrored channels older than {LIVE_STALE_HOURS:g}h",
                    (
                        f"inspect `slack-mirror --config {target.config_path} mirror status --workspace {name} "
                        f"--healthy --enforce-stale --stale-hours {LIVE_STALE_HOURS:g} --classify-access` "
                        "to distinguish quiet channels from real mirror gaps"
                    ),
                )

        workspace_reports.append(
            LiveValidationWorkspace(
                name=name,
                event_errors=event_errors,
                embedding_errors=embedding_errors,
                event_pending=event_pending,
                embedding_pending=embedding_pending,
                daemon_heartbeat_age_seconds=daemon_heartbeat_age,
                active_recent_channels=access_summary["active_recent_channels"],
                shell_like_zero_message_channels=access_summary["shell_like_zero_message_channels"],
                unexpected_empty_channels=access_summary["unexpected_empty_channels"],
                stale_channels=stale_channels,
                stale_warning_suppressed=stale_warning_suppressed,
                reconcile_state_present=reconcile_state_present,
                reconcile_state_age_seconds=reconcile_state_age_seconds,
                reconcile_auth_mode="user" if reconcile_state_present else None,
                reconcile_iso_utc=reconcile_iso_utc,
                reconcile_attempted=reconcile_attempted,
                reconcile_downloaded=reconcile_downloaded,
                reconcile_warnings=reconcile_warnings,
                reconcile_failed=reconcile_failed,
                failure_codes=ws_failures,
                warning_codes=ws_warnings,
            )
        )

    return _finalize_live_validation_report(
        failures=failures,
        warnings=warnings,
        require_live_units=require_live_units,
        workspaces=workspace_reports,
    )


def _finalize_live_validation_report(
    *,
    failures: list[LiveValidationIssue],
    warnings: list[LiveValidationIssue],
    require_live_units: bool,
    workspaces: list[LiveValidationWorkspace],
) -> LiveValidationReport:
    failure_codes = sorted({item.code for item in failures})
    warning_codes = sorted({item.code for item in warnings})
    if failures:
        status = "fail"
        summary = f"Summary: FAIL ({len(failures)} failure{'s' if len(failures) != 1 else ''})"
        ok = False
        exit_code = 1
    elif warnings:
        status = "pass_with_warnings"
        summary = f"Summary: PASS with warnings ({len(warnings)})"
        ok = True
        exit_code = 0
    else:
        status = "pass"
        summary = "Summary: PASS"
        ok = True
        exit_code = 0
    return LiveValidationReport(
        ok=ok,
        status=status,
        require_live_units=require_live_units,
        exit_code=exit_code,
        summary=summary,
        failure_count=len(failures),
        warning_count=len(warnings),
        failure_codes=failure_codes,
        warning_codes=warning_codes,
        failures=failures,
        warnings=warnings,
        workspaces=workspaces,
    )


def _build_status_report(
    *,
    paths: UserEnvPaths | None = None,
    runner: RunFn = subprocess.run,
) -> UserEnvStatusReport:
    target = paths or default_user_env_paths()
    reconcile_workspaces: list[dict[str, Any]] = []
    service_units = sorted(
        {
            "slack-mirror-api.service",
            *[path.name for path in (target.home_dir / ".config" / "systemd" / "user").glob("slack-mirror-*.service")],
            *[path.name for path in (target.home_dir / ".config" / "systemd" / "user").glob("slack-mirror-*.timer")],
        }
    )
    states: dict[str, str] = {}
    for unit_name in dict.fromkeys(service_units):
        states[unit_name] = _systemctl_state(runner, unit_name)
    if target.config_path.exists():
        try:
            cfg = _load_managed_config(target)
            for ws in [ws for ws in cfg.get("workspaces", []) if ws.get("name") and ws.get("enabled", True)]:
                name = str(ws.get("name"))
                reconcile_state = load_reconcile_state(target.config_path, workspace=name, auth_mode="user")
                if reconcile_state:
                    age_seconds: float | None = None
                    reconcile_ts = reconcile_state.get("ts")
                    if reconcile_ts is not None:
                        try:
                            age_seconds = max(0.0, time.time() - float(reconcile_ts))
                        except (TypeError, ValueError):
                            age_seconds = None
                    reconcile_workspaces.append(
                        {
                            "name": name,
                            "auth_mode": "user",
                            "state_present": True,
                            "iso_utc": str(reconcile_state.get("iso_utc") or "") or None,
                            "age_seconds": age_seconds,
                            "attempted": int(reconcile_state.get("attempted") or 0),
                            "downloaded": int(reconcile_state.get("downloaded") or 0),
                            "warnings": int(reconcile_state.get("warnings") or 0),
                            "failed": int(reconcile_state.get("failed") or 0),
                        }
                    )
                else:
                    reconcile_workspaces.append(
                        {
                            "name": name,
                            "auth_mode": None,
                            "state_present": False,
                            "iso_utc": None,
                            "age_seconds": None,
                            "attempted": 0,
                            "downloaded": 0,
                            "warnings": 0,
                            "failed": 0,
                        }
                    )
        except Exception:
            pass
    return UserEnvStatusReport(
        wrapper_present=target.wrapper_path.exists(),
        api_wrapper_present=target.api_wrapper_path.exists(),
        mcp_wrapper_present=target.mcp_wrapper_path.exists(),
        api_service_present=target.api_service_path.exists(),
        rollback_snapshot_present=target.backup_app_dir.exists(),
        config_present=target.config_path.exists(),
        db_present=(target.state_dir / "slack_mirror.db").exists(),
        cache_present=target.cache_dir.exists(),
        services=states,
        reconcile_workspaces=reconcile_workspaces,
    )


def _status_report_payload(report: UserEnvStatusReport) -> dict[str, Any]:
    return {
        "wrapper_present": report.wrapper_present,
        "api_wrapper_present": report.api_wrapper_present,
        "mcp_wrapper_present": report.mcp_wrapper_present,
        "api_service_present": report.api_service_present,
        "rollback_snapshot_present": report.rollback_snapshot_present,
        "config_present": report.config_present,
        "db_present": report.db_present,
        "cache_present": report.cache_present,
        "services": report.services,
        "reconcile_workspaces": report.reconcile_workspaces,
    }


def _live_validation_report_payload(report: LiveValidationReport) -> dict[str, Any]:
    return {
        "ok": report.ok,
        "status": report.status,
        "require_live_units": report.require_live_units,
        "exit_code": report.exit_code,
        "summary": report.summary,
        "failure_count": report.failure_count,
        "warning_count": report.warning_count,
        "failure_codes": report.failure_codes,
        "warning_codes": report.warning_codes,
        "failures": [
            {
                "severity": item.severity,
                "code": item.code,
                "message": item.message,
                "action": item.action,
                "workspace": item.workspace,
            }
            for item in report.failures
        ],
        "warnings": [
            {
                "severity": item.severity,
                "code": item.code,
                "message": item.message,
                "action": item.action,
                "workspace": item.workspace,
            }
            for item in report.warnings
        ],
        "workspaces": [
            {
                "name": workspace.name,
                "event_errors": workspace.event_errors,
                "embedding_errors": workspace.embedding_errors,
                "event_pending": workspace.event_pending,
                "embedding_pending": workspace.embedding_pending,
                "daemon_heartbeat_age_seconds": workspace.daemon_heartbeat_age_seconds,
                "active_recent_channels": workspace.active_recent_channels,
                "shell_like_zero_message_channels": workspace.shell_like_zero_message_channels,
                "unexpected_empty_channels": workspace.unexpected_empty_channels,
                "stale_channels": workspace.stale_channels,
                "stale_warning_suppressed": workspace.stale_warning_suppressed,
                "reconcile_state_present": workspace.reconcile_state_present,
                "reconcile_state_age_seconds": workspace.reconcile_state_age_seconds,
                "reconcile_auth_mode": workspace.reconcile_auth_mode,
                "reconcile_iso_utc": workspace.reconcile_iso_utc,
                "reconcile_attempted": workspace.reconcile_attempted,
                "reconcile_downloaded": workspace.reconcile_downloaded,
                "reconcile_warnings": workspace.reconcile_warnings,
                "reconcile_failed": workspace.reconcile_failed,
                "failure_codes": workspace.failure_codes,
                "warning_codes": workspace.warning_codes,
            }
            for workspace in report.workspaces
        ],
    }


def _finalize_live_smoke_report(
    *,
    failures: list[LiveValidationIssue],
    warnings: list[LiveValidationIssue],
    status_report: UserEnvStatusReport,
    validation_report: LiveValidationReport,
) -> LiveSmokeCheckReport:
    failure_codes = sorted({item.code for item in failures})
    warning_codes = sorted({item.code for item in warnings})
    if failures:
        return LiveSmokeCheckReport(
            ok=False,
            status="fail",
            exit_code=1,
            summary=f"Summary: FAIL ({len(failures)} failure{'s' if len(failures) != 1 else ''})",
            failure_count=len(failures),
            warning_count=len(warnings),
            failure_codes=failure_codes,
            warning_codes=warning_codes,
            failures=failures,
            warnings=warnings,
            status_report=status_report,
            validation_report=validation_report,
        )
    if warnings:
        return LiveSmokeCheckReport(
            ok=True,
            status="pass_with_warnings",
            exit_code=0,
            summary=f"Summary: PASS with warnings ({len(warnings)})",
            failure_count=0,
            warning_count=len(warnings),
            failure_codes=[],
            warning_codes=warning_codes,
            failures=[],
            warnings=warnings,
            status_report=status_report,
            validation_report=validation_report,
        )
    return LiveSmokeCheckReport(
        ok=True,
        status="pass",
        exit_code=0,
        summary="Summary: PASS",
        failure_count=0,
        warning_count=0,
        failure_codes=[],
        warning_codes=[],
        failures=[],
        warnings=[],
        status_report=status_report,
        validation_report=validation_report,
    )


def _build_live_smoke_report(
    *,
    paths: UserEnvPaths | None = None,
    runner: RunFn = subprocess.run,
) -> LiveSmokeCheckReport:
    target = paths or default_user_env_paths()
    status_report = _build_status_report(paths=target, runner=runner)
    validation_report = _build_live_validation_report(paths=target, runner=runner, require_live_units=True)
    failures = list(validation_report.failures)
    warnings = list(validation_report.warnings)

    def fail(code: str, message: str, action: str | None = None) -> None:
        failures.append(LiveValidationIssue("fail", code, message, action=action))

    if not status_report.wrapper_present:
        fail(
            "USER_WRAPPER_MISSING",
            "slack-mirror-user wrapper missing",
            "run `slack-mirror user-env update` to restore the managed CLI wrapper",
        )
    if not status_report.api_wrapper_present:
        fail(
            "API_WRAPPER_MISSING",
            "slack-mirror-api wrapper missing",
            "run `slack-mirror user-env update` to restore the managed API launcher",
        )
    if not status_report.mcp_wrapper_present:
        fail(
            "MCP_WRAPPER_MISSING",
            "slack-mirror-mcp wrapper missing",
            "run `slack-mirror user-env update` to restore the managed MCP launcher",
        )
    if not status_report.api_service_present:
        fail(
            "API_SERVICE_FILE_MISSING",
            "managed API service unit file missing",
            "run `slack-mirror user-env update` to recreate slack-mirror-api.service",
        )

    return _finalize_live_smoke_report(
        failures=failures,
        warnings=warnings,
        status_report=status_report,
        validation_report=validation_report,
    )


def _finalize_live_recovery_report(
    *,
    actions: list[LiveRecoveryAction],
    operator_only_issues: list[LiveValidationIssue],
    smoke_report: LiveSmokeCheckReport,
    applied: bool,
) -> LiveRecoveryReport:
    actionable_codes = sorted({item.code for item in actions})
    operator_only_codes = sorted({item.code for item in operator_only_issues})
    if actions:
        status = "actionable"
        summary = f"Summary: ACTIONABLE ({len(actions)} safe remediation{'s' if len(actions) != 1 else ''})"
        ok = True
        exit_code = 0
    elif operator_only_issues:
        status = "operator_only"
        summary = f"Summary: OPERATOR_ONLY ({len(operator_only_issues)} issue{'s' if len(operator_only_issues) != 1 else ''})"
        ok = False
        exit_code = 1
    else:
        status = "pass"
        summary = "Summary: PASS"
        ok = True
        exit_code = 0
    return LiveRecoveryReport(
        ok=ok,
        status=status,
        exit_code=exit_code,
        applied=applied,
        summary=summary,
        actionable_count=len(actions),
        operator_only_count=len(operator_only_issues),
        action_codes=actionable_codes,
        operator_only_codes=operator_only_codes,
        actions=actions,
        operator_only_issues=operator_only_issues,
        smoke_report=smoke_report,
    )


def _build_live_recovery_report(
    *,
    paths: UserEnvPaths | None = None,
    runner: RunFn = subprocess.run,
    applied: bool = False,
) -> LiveRecoveryReport:
    smoke_report = _build_live_smoke_report(paths=paths, runner=runner)
    actions: list[LiveRecoveryAction] = []
    operator_only_issues: list[LiveValidationIssue] = []
    seen_actions: set[tuple[str, str | None]] = set()

    def add_action(code: str, description: str, command: list[str], *, workspace: str | None = None) -> None:
        key = (code, workspace)
        if key in seen_actions:
            return
        seen_actions.add(key)
        actions.append(LiveRecoveryAction(code=code, description=description, command=command, safe=True, workspace=workspace))

    for issue in smoke_report.failures:
        if issue.code == "API_UNIT_INACTIVE":
            add_action(
                "RESTART_API_UNIT",
                "restart the managed API service",
                ["systemctl", "--user", "restart", "slack-mirror-api.service"],
            )
        elif issue.code == "LIVE_UNIT_INACTIVE" and issue.workspace:
            add_action(
                "RESTART_WORKSPACE_UNITS",
                f"restart the managed live units for workspace {issue.workspace}",
                [
                    "systemctl",
                    "--user",
                    "restart",
                    f"slack-mirror-webhooks-{issue.workspace}.service",
                    f"slack-mirror-daemon-{issue.workspace}.service",
                ],
                workspace=issue.workspace,
            )
        else:
            operator_only_issues.append(issue)

    return _finalize_live_recovery_report(
        actions=actions,
        operator_only_issues=operator_only_issues,
        smoke_report=smoke_report,
        applied=applied,
    )


def _run_migrations(paths: UserEnvPaths, *, runner: RunFn, out: PrintFn) -> None:
    _log(out, "running schema migrations (mirror init)")
    env = _runtime_env(paths)
    venv_python = str(paths.venv_dir / "bin" / "python")
    base = [venv_python, "-m", "slack_mirror.cli.main", "--config", str(paths.config_path)]
    _run(runner, [*base, "mirror", "init"], env=env)
    _log(out, "syncing workspace definitions")
    _run(runner, [*base, "workspaces", "sync-config"], env=env)


def install_user_env(
    *,
    paths: UserEnvPaths | None = None,
    runner: RunFn = subprocess.run,
    python_executable: str | None = None,
    out: PrintFn = print,
) -> int:
    target = paths or default_user_env_paths()
    _log(out, "installing isolated user environment")
    _ensure_dirs(target)
    _write_env_file(target)
    _copy_repo_snapshot(target)
    _ensure_venv(target, runner=runner, python_executable=python_executable, out=out)
    _install_python_package(target, runner=runner, out=out)
    _ensure_config(target, out=out)
    _migrate_legacy_state(target, out=out)
    _write_wrappers(target)
    _write_api_service(target)
    _write_snapshot_report_units(target)
    _run_migrations(target, runner=runner, out=out)
    runner(["systemctl", "--user", "daemon-reload"], check=False, text=True)
    runner(["systemctl", "--user", "enable", "--now", "slack-mirror-api.service"], check=False, text=True)
    runner(["systemctl", "--user", "enable", "--now", "slack-mirror-runtime-report.timer"], check=False, text=True)
    _log(out, "running managed-runtime validation")
    validation_rc = validate_live_user_env(paths=target, runner=runner, out=out, require_live_units=False)
    if validation_rc != 0:
        return validation_rc
    _log(out, "install complete")
    out("")
    out(f"CLI wrapper: {target.wrapper_path}")
    out(f"API wrapper:  {target.api_wrapper_path}")
    out(f"MCP wrapper:  {target.mcp_wrapper_path}")
    out(f"API unit:    {target.api_service_path}")
    out(f"Config:      {target.config_path}")
    out(f"State dir:   {target.state_dir}")
    out(f"Cache dir:   {target.cache_dir}")
    out("")
    out("Next: edit config and run:")
    out(f"  {target.wrapper_path} workspaces verify")
    return 0


def update_user_env(
    *,
    paths: UserEnvPaths | None = None,
    runner: RunFn = subprocess.run,
    python_executable: str | None = None,
    out: PrintFn = print,
) -> int:
    target = paths or default_user_env_paths()
    _log(out, "updating isolated user environment from current repo")
    _ensure_dirs(target)
    if not target.env_path.exists():
        _write_env_file(target)
    _rotate_app_snapshot_backup(target, out=out)
    _copy_repo_snapshot(target)
    _ensure_venv(target, runner=runner, python_executable=python_executable, out=out)
    _install_python_package(target, runner=runner, out=out)
    _ensure_config(target, out=out)
    _migrate_legacy_state(target, out=out)
    _write_wrappers(target)
    _write_api_service(target)
    _write_snapshot_report_units(target)
    _run_migrations(target, runner=runner, out=out)
    runner(["systemctl", "--user", "daemon-reload"], check=False, text=True)
    runner(["systemctl", "--user", "restart", "slack-mirror-api.service"], check=False, text=True)
    runner(["systemctl", "--user", "enable", "--now", "slack-mirror-runtime-report.timer"], check=False, text=True)
    _log(out, "running managed-runtime validation")
    validation_rc = validate_live_user_env(paths=target, runner=runner, out=out, require_live_units=False)
    if validation_rc != 0:
        return validation_rc
    _log(out, "update complete (config + DB preserved)")
    out(f"Latest config template saved at: {target.config_dir / 'config.example.latest.yaml'}")
    out(f"Rollback snapshot: {target.backup_app_dir}")
    out("If this update is bad, run `slack-mirror user-env rollback` to restore the previous app snapshot.")
    return 0


def rollback_user_env(
    *,
    paths: UserEnvPaths | None = None,
    runner: RunFn = subprocess.run,
    python_executable: str | None = None,
    out: PrintFn = print,
) -> int:
    target = paths or default_user_env_paths()
    _log(out, "rolling back isolated user environment to previous app snapshot")
    _ensure_dirs(target)
    if not target.env_path.exists():
        _write_env_file(target)
    if not target.backup_app_dir.exists():
        out(f"No rollback snapshot found at: {target.backup_app_dir}")
        out("Run `slack-mirror user-env update` at least once before using rollback.")
        return 1

    _swap_app_snapshot_with_backup(target, out=out)
    _ensure_venv(target, runner=runner, python_executable=python_executable, out=out)
    _install_python_package(target, runner=runner, out=out)
    _ensure_config(target, out=out)
    _migrate_legacy_state(target, out=out)
    _write_wrappers(target)
    _write_api_service(target)
    _write_snapshot_report_units(target)
    runner(["systemctl", "--user", "daemon-reload"], check=False, text=True)
    runner(["systemctl", "--user", "restart", "slack-mirror-api.service"], check=False, text=True)
    runner(["systemctl", "--user", "enable", "--now", "slack-mirror-runtime-report.timer"], check=False, text=True)
    _log(out, "running managed-runtime validation")
    validation_rc = validate_live_user_env(paths=target, runner=runner, out=out, require_live_units=False)
    if validation_rc != 0:
        return validation_rc
    _log(out, "rollback complete (config + DB preserved)")
    out("Rollback restored the previous app snapshot and refreshed the managed venv/wrappers.")
    out("Rollback does not reverse DB schema, queue contents, or other runtime state changes.")
    return 0


def uninstall_user_env(
    *,
    purge_data: bool = False,
    paths: UserEnvPaths | None = None,
    runner: RunFn = subprocess.run,
    out: PrintFn = print,
) -> int:
    target = paths or default_user_env_paths()
    _log(out, "stopping/removing user services if present")
    legacy_units = [
        "slack-mirror-webhooks.service",
        "slack-mirror-events.service",
        "slack-mirror-embeddings.service",
        "slack-mirror-api.service",
        "slack-mirror-runtime-report.service",
        "slack-mirror-runtime-report.timer",
    ]
    runner(["systemctl", "--user", "disable", "--now", *legacy_units], check=False, text=True)
    for unit_name in legacy_units:
        unit_path = target.home_dir / ".config" / "systemd" / "user" / unit_name
        if unit_path.exists():
            unit_path.unlink()
    runner(["systemctl", "--user", "daemon-reload"], check=False, text=True)

    _log(out, "removing wrapper + app + venv")
    for wrapper in (target.wrapper_path, target.api_wrapper_path, target.mcp_wrapper_path):
        if wrapper.exists():
            wrapper.unlink()
    if target.api_service_path.exists():
        target.api_service_path.unlink()
    if target.snapshot_service_path.exists():
        target.snapshot_service_path.unlink()
    if target.snapshot_timer_path.exists():
        target.snapshot_timer_path.unlink()
    if target.app_dir.exists():
        shutil.rmtree(target.app_dir)
    if target.backup_app_dir.exists():
        shutil.rmtree(target.backup_app_dir)
    if target.venv_dir.exists():
        shutil.rmtree(target.venv_dir)

    if purge_data:
        _log(out, "purging config + data")
        for path in (target.config_dir, target.state_dir, target.cache_dir):
            if path.exists():
                shutil.rmtree(path)
    else:
        _log(out, "preserving config + data")

    _log(out, "uninstall complete")
    return 0


def status_user_env(
    *,
    paths: UserEnvPaths | None = None,
    runner: RunFn = subprocess.run,
    out: PrintFn = print,
    json_output: bool = False,
) -> int:
    target = paths or default_user_env_paths()
    report = _build_status_report(paths=target, runner=runner)
    if json_output:
        out(json.dumps(_status_report_payload(report), indent=2, sort_keys=True))
        return 0
    db_path = target.state_dir / "slack_mirror.db"
    out(f"Wrapper:  {target.wrapper_path}")
    out("  status: present" if target.wrapper_path.exists() else "  status: missing")
    out(f"API:      {target.api_wrapper_path}")
    out("  status: present" if target.api_wrapper_path.exists() else "  status: missing")
    out(f"MCP:      {target.mcp_wrapper_path}")
    out("  status: present" if target.mcp_wrapper_path.exists() else "  status: missing")
    out(f"API svc:  {target.api_service_path}")
    out("  status: present" if target.api_service_path.exists() else "  status: missing")
    out(f"Rpt svc:  {target.snapshot_service_path}")
    out("  status: present" if target.snapshot_service_path.exists() else "  status: missing")
    out(f"Rpt tmr:  {target.snapshot_timer_path}")
    out("  status: present" if target.snapshot_timer_path.exists() else "  status: missing")
    out(f"Rollback: {target.backup_app_dir}")
    out("  status: present" if target.backup_app_dir.exists() else "  status: missing")
    out(f"Config:   {target.config_path}")
    out("  status: present" if target.config_path.exists() else "  status: missing")
    out(f"DB:       {db_path}")
    out("  status: present" if db_path.exists() else "  status: missing")
    out(f"Cache:    {target.cache_dir}")
    out("  status: present" if target.cache_dir.exists() else "  status: missing")
    out("Services:")
    completed = runner(
        ["systemctl", "--user", "--no-pager", "--full", "list-units", "slack-mirror*", "--all", "--plain"],
        check=False,
        text=True,
        capture_output=True,
    )
    stdout = (completed.stdout or "").strip()
    out(stdout if stdout else "  status: unavailable")
    if report.reconcile_workspaces:
        out("Reconcile state:")
        for item in report.reconcile_workspaces:
            if not item["state_present"]:
                out(f"  {item['name']}: missing")
                continue
            age_fragment = ""
            if item["age_seconds"] is not None:
                age_fragment = f", age={int(item['age_seconds'])}s"
            out(
                f"  {item['name']}: downloaded={item['downloaded']} warnings={item['warnings']} "
                f"failed={item['failed']}{age_fragment}"
            )
    return 0


def validate_live_user_env(
    *,
    paths: UserEnvPaths | None = None,
    runner: RunFn = subprocess.run,
    out: PrintFn = print,
    require_live_units: bool = True,
    json_output: bool = False,
) -> int:
    target = paths or default_user_env_paths()
    report = _build_live_validation_report(
        paths=target,
        runner=runner,
        require_live_units=require_live_units,
    )
    if json_output:
        out(json.dumps(_live_validation_report_payload(report), indent=2, sort_keys=True))
        return report.exit_code

    def emit_actions(items: list[LiveValidationIssue], *, label: str) -> None:
        actions: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            code = item.code
            action = item.action
            if not action:
                continue
            key = (code, action)
            if key in seen:
                continue
            seen.add(key)
            actions.append(key)
        if not actions:
            return
        out(label)
        for code, action in actions:
            out(f"  [{code}] {action}")

    out(f"Config: {target.config_path}")
    if target.config_path.exists():
        out("OK    managed config present")
        try:
            cfg = _load_managed_config(target)
            db_path = Path(str(cfg.get("storage", {}).get("db_path", target.state_dir / "slack_mirror.db"))).expanduser()
            out(f"DB:     {db_path}")
            if db_path.exists():
                out("OK    managed DB present")
        except Exception:
            pass

    if target.api_service_path.exists():
        out("OK    slack-mirror-api.service unit file present")
    if _systemctl_state(runner, "slack-mirror-api.service") == "active":
        out("OK    slack-mirror-api.service active")

    for workspace in report.workspaces:
        if "WORKSPACE_DB_MISSING" not in workspace.failure_codes:
            out(f"OK    workspace {workspace.name} synced into DB")
        if "OUTBOUND_TOKEN_MISSING" not in workspace.failure_codes:
            out(f"OK    workspace {workspace.name} explicit outbound bot token configured")
        if workspace.stale_warning_suppressed:
            out(
                "OK    "
                f"workspace {workspace.name} stale mirror evidence suppressed "
                f"({workspace.stale_channels} stale, {workspace.active_recent_channels} active_recent, "
                f"{workspace.unexpected_empty_channels} unexpected_empty)"
            )
        if workspace.reconcile_state_present:
            age_fragment = ""
            if workspace.reconcile_state_age_seconds is not None:
                age_fragment = f", age={int(workspace.reconcile_state_age_seconds)}s"
            out(
                "OK    "
                f"workspace {workspace.name} last reconcile-files "
                f"(downloaded={workspace.reconcile_downloaded}, warnings={workspace.reconcile_warnings}, "
                f"failed={workspace.reconcile_failed}{age_fragment})"
            )

    for issue in report.failures:
        out(f"FAIL  [{issue.code}] {issue.message}")
    for issue in report.warnings:
        out(f"WARN  [{issue.code}] {issue.message}")

    out(report.summary)
    if report.failures:
        emit_actions(report.failures, label="Recovery:")
        emit_actions(report.warnings, label="Warnings:")
    elif report.warnings:
        emit_actions(report.warnings, label="Warnings:")
    return report.exit_code


def check_live_user_env(
    *,
    paths: UserEnvPaths | None = None,
    runner: RunFn = subprocess.run,
    out: PrintFn = print,
    json_output: bool = False,
) -> int:
    target = paths or default_user_env_paths()
    report = _build_live_smoke_report(paths=target, runner=runner)

    if json_output:
        out(
            json.dumps(
                {
                    "ok": report.ok,
                    "status": report.status,
                    "exit_code": report.exit_code,
                    "summary": report.summary,
                    "failure_count": report.failure_count,
                    "warning_count": report.warning_count,
                    "failure_codes": report.failure_codes,
                    "warning_codes": report.warning_codes,
                    "failures": [
                        {
                            "severity": item.severity,
                            "code": item.code,
                            "message": item.message,
                            "action": item.action,
                            "workspace": item.workspace,
                        }
                        for item in report.failures
                    ],
                    "warnings": [
                        {
                            "severity": item.severity,
                            "code": item.code,
                            "message": item.message,
                            "action": item.action,
                            "workspace": item.workspace,
                        }
                        for item in report.warnings
                    ],
                    "status_report": _status_report_payload(report.status_report),
                    "validation_report": _live_validation_report_payload(report.validation_report),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return report.exit_code

    out("Managed Runtime:")
    out(f"  wrapper: {'present' if report.status_report.wrapper_present else 'missing'}")
    out(f"  api wrapper: {'present' if report.status_report.api_wrapper_present else 'missing'}")
    out(f"  mcp wrapper: {'present' if report.status_report.mcp_wrapper_present else 'missing'}")
    out(f"  api unit file: {'present' if report.status_report.api_service_present else 'missing'}")
    out("")
    out("Live Validation:")
    validate_live_user_env(paths=target, runner=runner, out=out, require_live_units=True, json_output=False)

    wrapper_failures = [item for item in report.failures if item.code in {
        "USER_WRAPPER_MISSING",
        "API_WRAPPER_MISSING",
        "MCP_WRAPPER_MISSING",
        "API_SERVICE_FILE_MISSING",
    }]
    if wrapper_failures:
        out("Managed Runtime Recovery:")
        seen: set[tuple[str, str | None]] = set()
        for item in wrapper_failures:
            key = (item.code, item.action)
            if key in seen:
                continue
            seen.add(key)
            if item.action:
                out(f"  [{item.code}] {item.action}")
    out(f"Combined {report.summary}")
    return report.exit_code


def recover_live_user_env(
    *,
    paths: UserEnvPaths | None = None,
    runner: RunFn = subprocess.run,
    out: PrintFn = print,
    apply: bool = False,
    json_output: bool = False,
) -> int:
    target = paths or default_user_env_paths()
    initial = _build_live_recovery_report(paths=target, runner=runner, applied=False)

    if apply and initial.actions:
        runner(["systemctl", "--user", "daemon-reload"], check=False, text=True)
        for action in initial.actions:
            if action.command:
                runner(action.command, check=False, text=True)
        report = _build_live_recovery_report(paths=target, runner=runner, applied=True)
    else:
        report = initial

    if json_output:
        out(
            json.dumps(
                {
                    "ok": report.ok,
                    "status": report.status,
                    "exit_code": report.exit_code,
                    "applied": report.applied,
                    "summary": report.summary,
                    "actionable_count": report.actionable_count,
                    "operator_only_count": report.operator_only_count,
                    "action_codes": report.action_codes,
                    "operator_only_codes": report.operator_only_codes,
                    "actions": [
                        {
                            "code": item.code,
                            "description": item.description,
                            "command": item.command,
                            "safe": item.safe,
                            "workspace": item.workspace,
                        }
                        for item in report.actions
                    ],
                    "operator_only_issues": [
                        {
                            "severity": item.severity,
                            "code": item.code,
                            "message": item.message,
                            "action": item.action,
                            "workspace": item.workspace,
                        }
                        for item in report.operator_only_issues
                    ],
                    "smoke_report": {
                        "ok": report.smoke_report.ok,
                        "status": report.smoke_report.status,
                        "exit_code": report.smoke_report.exit_code,
                        "summary": report.smoke_report.summary,
                        "failure_codes": report.smoke_report.failure_codes,
                        "warning_codes": report.smoke_report.warning_codes,
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return report.exit_code

    if not report.actions and not report.operator_only_issues:
        out("Safe Recovery Plan:")
        out("  no remediation needed")
        out(report.summary)
        return report.exit_code

    out("Safe Recovery Plan:")
    if report.actions:
        for action in report.actions:
            scope = f" ({action.workspace})" if action.workspace else ""
            out(f"  [{action.code}]{scope} {action.description}")
            if action.command:
                out(f"    command: {' '.join(action.command)}")
    else:
        out("  no safe automatic remediations available")

    if report.operator_only_issues:
        out("Operator-Only Issues:")
        for issue in report.operator_only_issues:
            scope = f" ({issue.workspace})" if issue.workspace else ""
            out(f"  [{issue.code}]{scope} {issue.message}")
            if issue.action:
                out(f"    next: {issue.action}")

    if apply and initial.actions:
        out("Apply Mode:")
        out("  executed safe remediations and rebuilt the recovery plan")
    elif apply:
        out("Apply Mode:")
        out("  nothing safe to apply")

    out(report.summary)
    return report.exit_code
