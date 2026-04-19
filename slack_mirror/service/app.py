from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from slack_mirror.core import db
from slack_mirror.core.config import load_config
from slack_mirror.core.db import (
    apply_migrations,
    connect,
    get_derived_text,
    get_derived_text_chunks,
    get_workspace_by_name,
    list_workspaces,
    upsert_workspace,
)
from slack_mirror.exports import (
    build_export_manifest,
    delete_export_bundle,
    list_export_manifests,
    rename_export_bundle,
    resolve_export_base_urls,
    resolve_export_root,
)
from slack_mirror.core.slack_api import SlackApiClient
from slack_mirror.search.embeddings import build_embedding_provider, probe_embedding_provider
from slack_mirror.search.eval import dataset_rows, evaluate_corpus_search, evaluate_derived_text_search
from slack_mirror.service.frontend_auth import (
    FrontendAuthConfig,
    FrontendAuthIssueResult,
    FrontendAuthProvisionResult,
    FrontendAuthSession,
    frontend_auth_config,
    list_frontend_auth_sessions,
    login_frontend_user,
    logout_frontend_user,
    provision_frontend_user,
    register_frontend_user,
    revoke_frontend_auth_session,
    resolve_frontend_auth_session,
)
from slack_mirror.service.processor import process_pending_events
from slack_mirror.service.user_env import _build_live_validation_report, _build_status_report, _status_report_payload, default_user_env_paths
from slack_mirror.service.runtime_report import (
    delete_runtime_report_snapshot,
    get_runtime_report_manifest,
    list_runtime_report_manifests,
    rename_runtime_report_snapshot,
    write_runtime_report_snapshot,
)
from slack_mirror.search.corpus import search_corpus, search_corpus_multi, search_corpus_multi_page, search_corpus_page


@dataclass(frozen=True)
class WorkspaceStatusRow:
    workspace: str
    channel_class: str
    channels: int
    zero_msg_channels: int
    stale_channels: int
    mirrored_inactive_channels: int
    latest_ts: float | None
    health_reasons: list[str]


@dataclass(frozen=True)
class HealthSummary:
    status: str
    healthy: bool
    max_zero_msg: int
    max_stale: int
    stale_hours: float
    enforce_stale: bool
    unhealthy_rows: int


@dataclass(frozen=True)
class LiveValidationResult:
    ok: bool
    status: str = "unknown"
    require_live_units: bool = True
    summary: str = "Summary: UNKNOWN"
    lines: list[str] = field(default_factory=list)
    exit_code: int = 1
    failure_count: int = 0
    warning_count: int = 0
    failure_codes: list[str] = field(default_factory=list)
    warning_codes: list[str] = field(default_factory=list)
    workspaces: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RuntimeStatusResult:
    ok: bool
    wrappers_present: bool
    mcp_ready: bool
    mcp_multi_client_ready: bool
    api_service_present: bool
    config_present: bool
    db_present: bool
    cache_present: bool
    rollback_snapshot_present: bool
    mcp_smoke_error: str | None = None
    mcp_multi_client_error: str | None = None
    mcp_multi_client_clients: int = 0
    services: dict[str, str] = field(default_factory=dict)
    reconcile_workspaces: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RuntimeReportListResult:
    reports: list[dict[str, Any]] = field(default_factory=list)
    base_url_choices: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class LandingPageResult:
    runtime_status: dict[str, Any]
    latest_report: dict[str, Any] | None
    reports: list[dict[str, Any]] = field(default_factory=list)
    exports: list[dict[str, Any]] = field(default_factory=list)


class SlackMirrorAppService:
    def __init__(self, config_path: str | None = None):
        self.config = load_config(config_path)
        self.db_path = self.config.get("storage", {}).get("db_path", "./data/slack_mirror.db")
        self.migrations_dir = str(Path(__file__).resolve().parents[1] / "core" / "migrations")
        self._message_embedding_provider = None

    def connect(self):
        conn = connect(self.db_path)
        apply_migrations(conn, self.migrations_dir)
        return conn

    def message_embedding_provider(self):
        if self._message_embedding_provider is None:
            self._message_embedding_provider = build_embedding_provider(self.config.data)
        return self._message_embedding_provider

    def message_embedding_probe(self, *, model_id: str | None = None, smoke_texts: list[str] | None = None) -> dict[str, Any]:
        return probe_embedding_provider(self.config.data, model_id=model_id, smoke_texts=smoke_texts)

    def validate_live_runtime(self, *, require_live_units: bool = True) -> LiveValidationResult:
        default_paths = default_user_env_paths()
        paths = replace(default_paths, config_path=self.config.path)
        report = _build_live_validation_report(
            paths=paths,
            require_live_units=require_live_units,
        )

        lines: list[str] = []

        if Path(paths.config_path).exists():
            lines.append(f"Config: {paths.config_path}")
            lines.append("OK    managed config present")
            try:
                db_path = Path(str(self.config.get("storage", {}).get("db_path", paths.state_dir / "slack_mirror.db"))).expanduser()
                lines.append(f"DB:     {db_path}")
                if db_path.exists():
                    lines.append("OK    managed DB present")
            except Exception:
                pass

        if Path(paths.api_service_path).exists():
            lines.append("OK    slack-mirror-api.service unit file present")
        for workspace in report.workspaces:
            if "WORKSPACE_DB_MISSING" not in workspace.failure_codes:
                lines.append(f"OK    workspace {workspace.name} synced into DB")
            if "OUTBOUND_TOKEN_MISSING" not in workspace.failure_codes:
                lines.append(f"OK    workspace {workspace.name} explicit outbound bot token configured")
        for issue in report.failures:
            lines.append(f"FAIL  [{issue.code}] {issue.message}")
        for issue in report.warnings:
            lines.append(f"WARN  [{issue.code}] {issue.message}")
        lines.append(report.summary)

        return LiveValidationResult(
            ok=report.ok,
            status=report.status,
            require_live_units=require_live_units,
            summary=report.summary,
            lines=lines,
            exit_code=report.exit_code,
            failure_count=report.failure_count,
            warning_count=report.warning_count,
            failure_codes=report.failure_codes,
            warning_codes=report.warning_codes,
            workspaces=[
                {
                    "name": workspace.name,
                    "event_errors": workspace.event_errors,
                    "embedding_errors": workspace.embedding_errors,
                    "event_pending": workspace.event_pending,
                    "embedding_pending": workspace.embedding_pending,
                    "stale_channels": workspace.stale_channels,
                    "stale_warning_suppressed": workspace.stale_warning_suppressed,
                    "active_recent_channels": workspace.active_recent_channels,
                    "shell_like_zero_message_channels": workspace.shell_like_zero_message_channels,
                    "unexpected_empty_channels": workspace.unexpected_empty_channels,
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
        )

    def runtime_status(self) -> RuntimeStatusResult:
        default_paths = default_user_env_paths()
        paths = replace(default_paths, config_path=self.config.path)
        report = _build_status_report(paths=paths)
        payload = _status_report_payload(report)
        return RuntimeStatusResult(
            ok=all(
                [
                    report.wrapper_present,
                    report.api_wrapper_present,
                    report.mcp_wrapper_present,
                    report.mcp_smoke_ok,
                    report.mcp_multi_client_ok,
                    report.api_service_present,
                    report.config_present,
                    report.db_present,
                    report.cache_present,
                ]
            ),
            wrappers_present=all(
                [
                    report.wrapper_present,
                    report.api_wrapper_present,
                    report.mcp_wrapper_present,
                ]
            ),
            mcp_ready=report.mcp_wrapper_present and report.mcp_smoke_ok,
            mcp_multi_client_ready=report.mcp_wrapper_present and report.mcp_smoke_ok and report.mcp_multi_client_ok,
            api_service_present=report.api_service_present,
            config_present=report.config_present,
            db_present=report.db_present,
            cache_present=report.cache_present,
            rollback_snapshot_present=report.rollback_snapshot_present,
            mcp_smoke_error=report.mcp_smoke_error,
            mcp_multi_client_error=report.mcp_multi_client_error,
            mcp_multi_client_clients=report.mcp_multi_client_clients,
            services=payload["services"],
            reconcile_workspaces=payload["reconcile_workspaces"],
        )

    def list_runtime_reports(self) -> RuntimeReportListResult:
        base_url_choices = [
            {"audience": audience, "base_url": base_url}
            for audience, base_url in resolve_export_base_urls(self.config).items()
            if str(base_url).strip()
        ]
        return RuntimeReportListResult(
            reports=list_runtime_report_manifests(self.config.path),
            base_url_choices=base_url_choices,
        )

    def get_runtime_report(self, name: str) -> dict[str, Any] | None:
        return get_runtime_report_manifest(self.config.path, name)

    def latest_runtime_report(self) -> dict[str, Any] | None:
        reports = list_runtime_report_manifests(self.config.path)
        return reports[0] if reports else None

    def create_runtime_report(self, *, base_url: str, name: str, timeout: float = 5.0) -> dict[str, Any]:
        runtime_status_result = self.runtime_status()
        runtime_status = {"ok": runtime_status_result.ok, "status": runtime_status_result.__dict__}
        live_validation_result = self.validate_live_runtime(require_live_units=True)
        live_validation = {"ok": live_validation_result.ok, "validation": live_validation_result.__dict__}
        return write_runtime_report_snapshot(
            config_path=self.config.path,
            base_url=base_url,
            name=name,
            timeout=timeout,
            runtime_status=runtime_status,
            live_validation=live_validation,
        )

    def rename_runtime_report(self, *, name: str, new_name: str) -> dict[str, Any]:
        return rename_runtime_report_snapshot(self.config.path, name, new_name)

    def delete_runtime_report(self, *, name: str) -> bool:
        return delete_runtime_report_snapshot(self.config.path, name)

    def landing_page_data(self, *, export_audience: str = "local") -> LandingPageResult:
        runtime_status = self.runtime_status().__dict__
        reports = list_runtime_report_manifests(self.config.path)
        export_root = resolve_export_root(self.config)
        export_base_urls = resolve_export_base_urls(self.config)
        exports = list_export_manifests(
            export_root,
            base_urls=export_base_urls,
            default_audience=export_audience,
        )
        return LandingPageResult(
            runtime_status=runtime_status,
            latest_report=reports[0] if reports else None,
            reports=reports[:5],
            exports=exports[:6],
        )

    def create_channel_day_export(
        self,
        *,
        workspace: str,
        channel: str,
        day: str,
        tz: str = "America/Chicago",
        audience: str = "local",
        export_id: str | None = None,
    ) -> dict[str, Any]:
        export_root = resolve_export_root(self.config)
        script_path = Path(__file__).resolve().parents[2] / "scripts" / "export_channel_day.py"
        if not script_path.exists():
            raise FileNotFoundError(f"managed export script not found: {script_path}")
        args = [
            sys.executable,
            str(script_path),
            "--config",
            str(self.config.path),
            "--db",
            str(self.db_path),
            "--workspace",
            str(workspace),
            "--channel",
            str(channel),
            "--day",
            str(day),
            "--tz",
            str(tz),
            "--managed-export",
            "--link-audience",
            str(audience),
        ]
        if export_id:
            args.extend(["--export-id", str(export_id)])
        completed = subprocess.run(args, check=False, text=True, capture_output=True)
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            raise RuntimeError(stderr or stdout or f"channel-day export failed ({completed.returncode})")
        resolved_export_id = str(export_id or "").strip()
        if not resolved_export_id:
            lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
            bundle_line = next((line for line in lines if line.startswith("Export bundle: ")), "")
            if bundle_line:
                resolved_export_id = Path(bundle_line.removeprefix("Export bundle: ").strip()).name
        if not resolved_export_id:
            raise RuntimeError("channel-day export succeeded but export id could not be resolved")
        bundle_dir = export_root / resolved_export_id
        if not bundle_dir.exists() or not bundle_dir.is_dir():
            raise FileNotFoundError(f"export bundle not found after create: {resolved_export_id}")
        return build_export_manifest(
            bundle_dir,
            export_id=resolved_export_id,
            base_urls=resolve_export_base_urls(self.config),
            default_audience=audience,
        )

    def rename_export(self, *, export_id: str, new_export_id: str, audience: str = "local") -> dict[str, Any]:
        return rename_export_bundle(
            resolve_export_root(self.config),
            export_id=export_id,
            new_export_id=new_export_id,
            base_urls=resolve_export_base_urls(self.config),
            default_audience=audience,
        )

    def delete_export(self, *, export_id: str) -> bool:
        return delete_export_bundle(resolve_export_root(self.config), export_id)

    def frontend_auth_config(self) -> FrontendAuthConfig:
        return frontend_auth_config(self.config.data)

    def frontend_auth_status(self, conn) -> dict[str, Any]:
        cfg = self.frontend_auth_config()
        from slack_mirror.core.db import count_auth_users

        user_count = count_auth_users(conn)
        return {
            "enabled": cfg.enabled,
            "allow_registration": cfg.allow_registration,
            "registration_allowlist": list(cfg.registration_allowlist),
            "registration_allowlist_count": len(cfg.registration_allowlist),
            "registration_mode": (
                "closed"
                if not cfg.enabled or not cfg.allow_registration
                else "allowlisted"
                if cfg.registration_allowlist
                else "open"
            ),
            "cookie_name": cfg.cookie_name,
            "cookie_secure_mode": cfg.cookie_secure_mode,
            "session_days": cfg.session_days,
            "session_idle_timeout_seconds": cfg.session_idle_timeout_seconds,
            "login_attempt_window_seconds": cfg.login_attempt_window_seconds,
            "login_attempt_max_failures": cfg.login_attempt_max_failures,
            "user_count": user_count,
            "registration_open": cfg.enabled and cfg.allow_registration and not cfg.registration_allowlist,
        }

    def frontend_auth_session(self, conn, *, session_token: str | None) -> FrontendAuthSession:
        if not self.frontend_auth_config().enabled:
            return FrontendAuthSession(authenticated=False, auth_source="disabled")
        return resolve_frontend_auth_session(
            conn,
            session_token=session_token,
            session_idle_timeout_seconds=self.frontend_auth_config().session_idle_timeout_seconds,
        )

    def register_frontend_user(
        self,
        conn,
        *,
        username: str,
        password: str,
        display_name: str | None = None,
    ) -> FrontendAuthIssueResult:
        cfg = self.frontend_auth_config()
        if not cfg.enabled:
            raise ValueError("frontend auth is disabled")
        if not cfg.allow_registration:
            raise ValueError("registration is disabled")
        normalized_username = db.normalize_auth_username(username)
        if cfg.registration_allowlist and normalized_username not in set(cfg.registration_allowlist):
            raise ValueError("registration is restricted for this username")
        return register_frontend_user(
            conn,
            username=normalized_username,
            password=password,
            display_name=display_name,
            session_days=cfg.session_days,
        )

    def login_frontend_user(
        self,
        conn,
        *,
        username: str,
        password: str,
        remote_addr: str | None = None,
    ) -> FrontendAuthIssueResult:
        cfg = self.frontend_auth_config()
        if not cfg.enabled:
            raise ValueError("frontend auth is disabled")
        return login_frontend_user(
            conn,
            username=username,
            password=password,
            session_days=cfg.session_days,
            remote_addr=remote_addr,
            login_attempt_window_seconds=cfg.login_attempt_window_seconds,
            login_attempt_max_failures=cfg.login_attempt_max_failures,
        )

    def logout_frontend_user(self, conn, *, session_token: str | None) -> None:
        if not self.frontend_auth_config().enabled:
            return
        logout_frontend_user(conn, session_token=session_token)

    def list_frontend_auth_sessions(self, conn, *, auth_session: FrontendAuthSession) -> list[dict[str, Any]]:
        if not self.frontend_auth_config().enabled:
            raise ValueError("frontend auth is disabled")
        if not auth_session.authenticated or auth_session.user_id is None:
            raise ValueError("authentication required")
        return list_frontend_auth_sessions(
            conn,
            user_id=int(auth_session.user_id),
            session_idle_timeout_seconds=self.frontend_auth_config().session_idle_timeout_seconds,
        )

    def revoke_frontend_auth_session(
        self,
        conn,
        *,
        auth_session: FrontendAuthSession,
        session_id: int,
    ) -> bool:
        if not self.frontend_auth_config().enabled:
            raise ValueError("frontend auth is disabled")
        if not auth_session.authenticated or auth_session.user_id is None:
            raise ValueError("authentication required")
        return revoke_frontend_auth_session(conn, user_id=int(auth_session.user_id), session_id=int(session_id))

    def provision_frontend_user(
        self,
        conn,
        *,
        username: str,
        password: str,
        display_name: str | None = None,
        reset_password: bool = False,
    ) -> FrontendAuthProvisionResult:
        return provision_frontend_user(
            conn,
            username=username,
            password=password,
            display_name=display_name,
            reset_password=reset_password,
        )

    def workspace_configs(self) -> list[dict[str, Any]]:
        return self.config.get("workspaces", [])

    def workspace_config_by_name(self, name: str) -> dict[str, Any]:
        for ws in self.workspace_configs():
            if ws.get("name") == name:
                return ws
        raise ValueError(f"Workspace '{name}' not found in config")

    def workspace_id(self, conn, name: str) -> int:
        ws_cfg = self.workspace_config_by_name(name)
        ws_row = get_workspace_by_name(conn, name)
        if ws_row:
            return int(ws_row["id"])
        return upsert_workspace(
            conn,
            name=ws_cfg.get("name"),
            team_id=ws_cfg.get("team_id"),
            domain=ws_cfg.get("domain"),
            config=ws_cfg,
        )

    def _token_env_candidates(self, name: str, *, auth_mode: str, purpose: str) -> list[str]:
        mode = (auth_mode or "bot").lower()
        suffix = "USER_TOKEN" if mode == "user" else "BOT_TOKEN"
        workspace_key = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
        candidates: list[str] = []
        if purpose == "write":
            candidates.extend(
                [
                    f"SLACK_WRITE_{suffix}",
                    f"SLACK_{suffix}_WRITE",
                    f"SLACK_{workspace_key}_WRITE_{suffix}" if workspace_key else "",
                    f"SLACK_WRITE_{workspace_key}_{suffix}" if workspace_key else "",
                    f"SLACK_MIRROR_{workspace_key}_WRITE_{suffix}" if workspace_key else "",
                ]
            )
        candidates.extend(
            [
                f"SLACK_{workspace_key}_{suffix}" if workspace_key else "",
                f"SLACK_{suffix}_{workspace_key}" if workspace_key else "",
                f"SLACK_MIRROR_{workspace_key}_{suffix}" if workspace_key else "",
            ]
        )
        if name == "default":
            candidates.append(f"SLACK_{suffix}")
        return [candidate for candidate in candidates if candidate]

    def workspace_token(self, name: str, *, auth_mode: str = "bot", purpose: str = "read") -> str:
        ws_cfg = self.workspace_config_by_name(name)
        mode = (auth_mode or "bot").lower()
        if mode not in {"bot", "user"}:
            raise ValueError(f"Unsupported auth mode: {auth_mode}")
        if purpose not in {"read", "write"}:
            raise ValueError(f"Unsupported token purpose: {purpose}")

        primary_key = "user_token" if mode == "user" else "token"
        write_keys = ["outbound_user_token", "write_user_token"] if mode == "user" else ["outbound_token", "write_token"]
        candidate_keys = write_keys if purpose == "write" else [primary_key]

        token = None
        for key in candidate_keys:
            value = ws_cfg.get(key)
            if value:
                token = str(value)
                break

        if purpose == "write" and not token:
            for env_key in self._token_env_candidates(name, auth_mode=mode, purpose=purpose):
                value = os.environ.get(env_key)
                if value:
                    token = value
                    break

        if purpose == "write" and not token:
            value = ws_cfg.get(primary_key)
            if value:
                token = str(value)

        if not token:
            raise ValueError(f"Workspace '{name}' has no token configured for auth_mode={mode} purpose={purpose}")
        return str(token)

    def resolve_channel_ref(self, conn, workspace_id: int, channel_ref: str) -> str:
        ref = (channel_ref or "").strip()
        if not ref:
            raise ValueError("channel_ref is required")
        if re.match(r"^[A-Z][A-Z0-9]+$", ref):
            return ref
        row = conn.execute(
            """
            SELECT channel_id
            FROM channels
            WHERE workspace_id = ? AND lower(name) = lower(?)
            ORDER BY channel_id
            LIMIT 1
            """,
            (workspace_id, ref),
        ).fetchone()
        if row:
            return str(row["channel_id"])
        return ref

    def resolve_user_ref(self, conn, workspace_id: int, user_ref: str) -> str | None:
        ref = (user_ref or "").strip()
        if not ref:
            return None
        mention_match = re.fullmatch(r"<@([A-Z0-9]+)>", ref)
        if mention_match:
            ref = mention_match.group(1)
        if ref.startswith("@"):
            ref = ref[1:]
        if re.fullmatch(r"U[A-Z0-9]+", ref):
            row = conn.execute(
                "SELECT user_id FROM users WHERE workspace_id = ? AND user_id = ? LIMIT 1",
                (workspace_id, ref),
            ).fetchone()
            return str(row["user_id"]) if row else ref
        rows = conn.execute(
            """
            SELECT user_id
            FROM users
            WHERE workspace_id = ?
              AND (
                lower(coalesce(username, '')) = lower(?)
                OR lower(coalesce(display_name, '')) = lower(?)
                OR lower(coalesce(real_name, '')) = lower(?)
              )
            ORDER BY user_id
            LIMIT 2
            """,
            (workspace_id, ref, ref, ref),
        ).fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            raise ValueError(f"User reference '{user_ref}' is ambiguous in workspace")
        return str(rows[0]["user_id"])

    def resolve_outbound_channel(self, conn, *, workspace_id: int, channel_ref: str, client: SlackApiClient) -> str:
        ref = (channel_ref or "").strip()
        if not ref:
            raise ValueError("channel_ref is required")
        if re.fullmatch(r"[CDG][A-Z0-9]+", ref):
            return ref
        user_id = self.resolve_user_ref(conn, workspace_id, ref)
        if user_id:
            dm = client.open_direct_message(user_id=user_id)
            channel = dm.get("channel") or {}
            channel_id = channel.get("id")
            if not channel_id:
                raise ValueError(f"Failed to open direct message for user '{channel_ref}'")
            return str(channel_id)
        return self.resolve_channel_ref(conn, workspace_id, ref)

    def list_workspaces(self, conn) -> list[dict[str, Any]]:
        return [dict(row) for row in list_workspaces(conn)]

    def list_workspace_channels(self, conn, *, workspace: str) -> list[dict[str, Any]]:
        workspace_id = self.workspace_id(conn, workspace)
        rows = conn.execute(
            """
            SELECT
              c.channel_id,
              c.name,
              CASE
                WHEN c.is_im = 1 THEN 'im'
                WHEN c.is_mpim = 1 THEN 'mpim'
                WHEN c.is_private = 1 THEN 'private'
                ELSE 'public'
              END AS channel_class,
              COUNT(m.ts) AS message_count,
              MAX(CAST(m.ts AS REAL)) AS latest_message_ts
            FROM channels c
            LEFT JOIN messages m
              ON m.workspace_id = c.workspace_id
             AND m.channel_id = c.channel_id
             AND m.deleted = 0
            WHERE c.workspace_id = ?
            GROUP BY c.channel_id, c.name, c.is_im, c.is_mpim, c.is_private
            ORDER BY
              CASE WHEN MAX(CAST(m.ts AS REAL)) IS NULL THEN 1 ELSE 0 END,
              MAX(CAST(m.ts AS REAL)) DESC,
              lower(COALESCE(c.name, c.channel_id)) ASC
            """,
            (workspace_id,),
        ).fetchall()
        payload: list[dict[str, Any]] = []
        for row in rows:
            latest_ts = row["latest_message_ts"]
            latest_message_day = None
            if latest_ts is not None:
                latest_message_day = time.strftime("%Y-%m-%d", time.gmtime(float(latest_ts)))
            payload.append(
                {
                    "channel_id": str(row["channel_id"]),
                    "name": str(row["name"] or row["channel_id"]),
                    "channel_class": str(row["channel_class"]),
                    "message_count": int(row["message_count"] or 0),
                    "latest_message_ts": None if latest_ts is None else str(latest_ts),
                    "latest_message_day": latest_message_day,
                }
            )
        return payload

    def enabled_workspace_names(self) -> list[str]:
        names: list[str] = []
        for ws in self.workspace_configs():
            if ws.get("enabled", True) is False:
                continue
            name = str(ws.get("name") or "").strip()
            if name:
                names.append(name)
        return names

    def corpus_search(
        self,
        conn,
        *,
        workspace: str | None = None,
        all_workspaces: bool = False,
        query: str,
        limit: int = 20,
        offset: int = 0,
        mode: str = "hybrid",
        model_id: str = "local-hash-128",
        lexical_weight: float = 0.6,
        semantic_weight: float = 0.4,
        semantic_scale: float = 10.0,
        use_fts: bool = True,
        derived_kind: str | None = None,
        derived_source_kind: str | None = None,
        message_embedding_provider=None,
    ) -> list[dict[str, Any]]:
        provider = message_embedding_provider or self.message_embedding_provider()
        if all_workspaces:
            if workspace:
                raise ValueError("workspace must not be set when all_workspaces is true")
            scopes = [{"id": self.workspace_id(conn, name), "name": name} for name in self.enabled_workspace_names()]
            return search_corpus_multi(
                conn,
                workspaces=scopes,
                query=query,
                limit=limit,
                offset=offset,
                mode=mode,
                model_id=model_id,
                lexical_weight=lexical_weight,
                semantic_weight=semantic_weight,
                semantic_scale=semantic_scale,
                use_fts=use_fts,
                derived_kind=derived_kind,
                derived_source_kind=derived_source_kind,
                message_embedding_provider=provider,
            )

        if not workspace:
            raise ValueError("workspace is required unless all_workspaces is true")
        workspace_id = self.workspace_id(conn, workspace)
        return search_corpus(
            conn,
            workspace_id=workspace_id,
            workspace_name=workspace,
            query=query,
            limit=limit,
            offset=offset,
            mode=mode,
            model_id=model_id,
            lexical_weight=lexical_weight,
            semantic_weight=semantic_weight,
            semantic_scale=semantic_scale,
            use_fts=use_fts,
            derived_kind=derived_kind,
            derived_source_kind=derived_source_kind,
            message_embedding_provider=provider,
        )

    def corpus_search_page(
        self,
        conn,
        *,
        workspace: str | None = None,
        all_workspaces: bool = False,
        query: str,
        limit: int = 20,
        offset: int = 0,
        mode: str = "hybrid",
        model_id: str = "local-hash-128",
        lexical_weight: float = 0.6,
        semantic_weight: float = 0.4,
        semantic_scale: float = 10.0,
        use_fts: bool = True,
        derived_kind: str | None = None,
        derived_source_kind: str | None = None,
        message_embedding_provider=None,
    ) -> dict[str, Any]:
        provider = message_embedding_provider or self.message_embedding_provider()
        if all_workspaces:
            if workspace:
                raise ValueError("workspace must not be set when all_workspaces is true")
            scopes = [{"id": self.workspace_id(conn, name), "name": name} for name in self.enabled_workspace_names()]
            return search_corpus_multi_page(
                conn,
                workspaces=scopes,
                query=query,
                limit=limit,
                offset=offset,
                mode=mode,
                model_id=model_id,
                lexical_weight=lexical_weight,
                semantic_weight=semantic_weight,
                semantic_scale=semantic_scale,
                use_fts=use_fts,
                derived_kind=derived_kind,
                derived_source_kind=derived_source_kind,
                message_embedding_provider=provider,
            )

        if not workspace:
            raise ValueError("workspace is required unless all_workspaces is true")
        workspace_id = self.workspace_id(conn, workspace)
        return search_corpus_page(
            conn,
            workspace_id=workspace_id,
            workspace_name=workspace,
            query=query,
            limit=limit,
            offset=offset,
            mode=mode,
            model_id=model_id,
            lexical_weight=lexical_weight,
            semantic_weight=semantic_weight,
            semantic_scale=semantic_scale,
            use_fts=use_fts,
            derived_kind=derived_kind,
            derived_source_kind=derived_source_kind,
            message_embedding_provider=provider,
        )

    def get_message_detail(
        self,
        conn,
        *,
        workspace: str,
        channel_id: str,
        ts: str,
    ) -> dict[str, Any] | None:
        workspace_id = self.workspace_id(conn, workspace)
        row = conn.execute(
            """
            SELECT
              m.workspace_id,
              ? AS workspace,
              m.channel_id,
              c.name AS channel_name,
              m.ts,
              m.thread_ts,
              m.user_id,
              COALESCE(u.display_name, u.real_name, u.username, m.user_id) AS user_label,
              m.subtype,
              m.text,
              m.edited_ts,
              m.deleted,
              m.raw_json,
              m.created_at,
              m.updated_at
            FROM messages m
            LEFT JOIN channels c
              ON c.workspace_id = m.workspace_id
             AND c.channel_id = m.channel_id
            LEFT JOIN users u
              ON u.workspace_id = m.workspace_id
             AND u.user_id = m.user_id
            WHERE m.workspace_id = ?
              AND m.channel_id = ?
              AND m.ts = ?
            LIMIT 1
            """,
            (workspace, workspace_id, channel_id, ts),
        ).fetchone()
        if not row:
            return None
        payload = dict(row)
        try:
            payload["message"] = json.loads(payload.get("raw_json") or "{}")
        except json.JSONDecodeError:
            payload["message"] = {}
        return payload

    def get_derived_text_detail(
        self,
        conn,
        *,
        workspace: str,
        source_kind: str,
        source_id: str,
        derivation_kind: str,
        extractor: str | None = None,
    ) -> dict[str, Any] | None:
        workspace_id = self.workspace_id(conn, workspace)
        record = get_derived_text(
            conn,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
            derivation_kind=derivation_kind,
            extractor=extractor,
        )
        if not record:
            return None
        chunks = get_derived_text_chunks(conn, derived_text_id=int(record["id"]))
        return {
            **record,
            "workspace": workspace,
            "chunks": chunks,
        }

    def search_readiness(self, conn, *, workspace: str) -> dict[str, Any]:
        workspace_id = self.workspace_id(conn, workspace)
        embedding_probe = self.message_embedding_probe()
        configured_model = str(self.config.get("search", {}).get("semantic", {}).get("model", "local-hash-128"))

        message_count = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE workspace_id = ? AND deleted = 0",
                (workspace_id,),
            ).fetchone()["c"]
        )
        message_embedding_count = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM message_embeddings WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()["c"]
        )
        message_embedding_pending = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM embedding_jobs WHERE workspace_id = ? AND status = 'pending'",
                (workspace_id,),
            ).fetchone()["c"]
        )
        message_embedding_errors = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM embedding_jobs WHERE workspace_id = ? AND status = 'error'",
                (workspace_id,),
            ).fetchone()["c"]
        )
        message_embedding_model_rows = conn.execute(
            """
            SELECT model_id, COUNT(*) AS c
            FROM message_embeddings
            WHERE workspace_id = ?
            GROUP BY model_id
            ORDER BY model_id
            """,
            (workspace_id,),
        ).fetchall()
        embeddings_by_model = {str(row["model_id"]): int(row["c"]) for row in message_embedding_model_rows}
        configured_model_count = int(embeddings_by_model.get(configured_model, 0))
        configured_model_missing = max(message_count - configured_model_count, 0)
        configured_model_coverage_ratio = 1.0 if message_count <= 0 else configured_model_count / max(message_count, 1)

        derived_count_rows = conn.execute(
            """
            SELECT derivation_kind, COUNT(*) AS c
            FROM derived_text
            WHERE workspace_id = ?
            GROUP BY derivation_kind
            """,
            (workspace_id,),
        ).fetchall()
        derived_counts = {str(row["derivation_kind"]): int(row["c"]) for row in derived_count_rows}
        derived_chunk_rows = conn.execute(
            """
            SELECT dt.derivation_kind, COUNT(*) AS c
            FROM derived_text_chunks dc
            JOIN derived_text dt ON dt.id = dc.derived_text_id
            WHERE dt.workspace_id = ?
            GROUP BY dt.derivation_kind
            """,
            (workspace_id,),
        ).fetchall()
        derived_chunk_counts = {str(row["derivation_kind"]): int(row["c"]) for row in derived_chunk_rows}
        derived_chunk_embedding_rows = conn.execute(
            """
            SELECT dt.derivation_kind, dte.model_id, COUNT(*) AS c
            FROM derived_text_chunk_embeddings dte
            JOIN derived_text_chunks dc ON dc.id = dte.derived_text_chunk_id
            JOIN derived_text dt ON dt.id = dc.derived_text_id
            WHERE dt.workspace_id = ?
            GROUP BY dt.derivation_kind, dte.model_id
            ORDER BY dt.derivation_kind, dte.model_id
            """,
            (workspace_id,),
        ).fetchall()
        derived_chunk_embeddings_by_model: dict[str, dict[str, int]] = {"attachment_text": {}, "ocr_text": {}}
        for row in derived_chunk_embedding_rows:
            kind = str(row["derivation_kind"])
            if kind not in derived_chunk_embeddings_by_model:
                derived_chunk_embeddings_by_model[kind] = {}
            derived_chunk_embeddings_by_model[kind][str(row["model_id"])] = int(row["c"])

        provider_rows = conn.execute(
            """
            SELECT derivation_kind, metadata_json
            FROM derived_text
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchall()
        provider_counts: dict[str, dict[str, int]] = {"attachment_text": {}, "ocr_text": {}}
        for row in provider_rows:
            kind = str(row["derivation_kind"])
            if kind not in provider_counts:
                provider_counts[kind] = {}
            metadata = json.loads(row["metadata_json"] or "{}")
            provider = str(metadata.get("provider") or "unknown")
            provider_counts[kind][provider] = provider_counts[kind].get(provider, 0) + 1

        job_rows = conn.execute(
            """
            SELECT derivation_kind, status, COALESCE(error, '') AS error_value, COUNT(*) AS c
            FROM derived_text_jobs
            WHERE workspace_id = ?
            GROUP BY derivation_kind, status, error_value
            """,
            (workspace_id,),
        ).fetchall()
        job_counts: dict[str, dict[str, int]] = {
            "attachment_text": {"pending": 0, "done": 0, "skipped": 0, "error": 0},
            "ocr_text": {"pending": 0, "done": 0, "skipped": 0, "error": 0},
        }
        issue_reasons: dict[str, dict[str, int]] = {"attachment_text": {}, "ocr_text": {}}
        for row in job_rows:
            kind = str(row["derivation_kind"])
            status = str(row["status"])
            count = int(row["c"])
            if kind not in job_counts:
                job_counts[kind] = {"pending": 0, "done": 0, "skipped": 0, "error": 0}
                issue_reasons[kind] = {}
            job_counts[kind][status] = job_counts[kind].get(status, 0) + count
            error_value = str(row["error_value"] or "")
            if error_value:
                issue_reasons[kind][error_value] = issue_reasons[kind].get(error_value, 0) + count

        derived_text = {}
        for kind in sorted(set(derived_counts) | set(job_counts) | {"attachment_text", "ocr_text"}):
            jobs = job_counts.get(kind, {"pending": 0, "done": 0, "skipped": 0, "error": 0})
            chunk_count = int(derived_chunk_counts.get(kind, 0))
            chunk_model_counts = dict(derived_chunk_embeddings_by_model.get(kind, {}))
            chunk_model_count = int(chunk_model_counts.get(configured_model, 0))
            chunk_model_missing = max(chunk_count - chunk_model_count, 0)
            chunk_model_coverage_ratio = 1.0 if chunk_count <= 0 else chunk_model_count / max(chunk_count, 1)
            derived_text[kind] = {
                "count": derived_counts.get(kind, 0),
                "chunk_count": chunk_count,
                "chunk_embeddings_by_model": chunk_model_counts,
                "configured_model_chunk_count": chunk_model_count,
                "configured_model_chunk_missing": chunk_model_missing,
                "configured_model_chunk_coverage_ratio": round(chunk_model_coverage_ratio, 6),
                "configured_model_chunk_ready": chunk_model_missing == 0,
                "pending": jobs.get("pending", 0),
                "errors": jobs.get("error", 0),
                "providers": provider_counts.get(kind, {}),
                "jobs": jobs,
                "issue_reasons": issue_reasons.get(kind, {}),
            }

        return {
            "workspace": workspace,
            "messages": {
                "count": message_count,
                "embeddings": {
                    "count": message_embedding_count,
                    "pending": message_embedding_pending,
                    "errors": message_embedding_errors,
                    "provider": str(embedding_probe.get("provider_type") or "unknown"),
                    "model": configured_model,
                    "configured_model_count": configured_model_count,
                    "configured_model_missing": configured_model_missing,
                    "configured_model_coverage_ratio": round(configured_model_coverage_ratio, 6),
                    "configured_model_ready": configured_model_missing == 0,
                    "by_model": embeddings_by_model,
                    "probe": embedding_probe,
                },
            },
            "derived_text": derived_text,
            "status": "ready"
            if message_count > 0 and message_embedding_errors == 0 and derived_text["attachment_text"]["errors"] == 0 and derived_text["ocr_text"]["errors"] == 0
            else "degraded",
        }

    def search_health(
        self,
        conn,
        *,
        workspace: str,
        dataset_path: str | None = None,
        benchmark_target: str = "corpus",
        mode: str = "hybrid",
        limit: int = 10,
        model_id: str = "local-hash-128",
        min_hit_at_3: float = 0.5,
        min_hit_at_10: float = 0.8,
        min_ndcg_at_k: float = 0.6,
        max_latency_p95_ms: float = 800.0,
        max_attachment_pending: int = 25,
        max_ocr_pending: int = 25,
    ) -> dict[str, Any]:
        if benchmark_target == "derived_text" and mode not in {"lexical", "semantic"}:
            raise ValueError("derived_text benchmark target only supports lexical or semantic mode")

        readiness = self.search_readiness(conn, workspace=workspace)
        workspace_id = self.workspace_id(conn, workspace)

        report: dict[str, Any] = {
            "workspace": workspace,
            "status": "pass" if readiness["status"] == "ready" else "degraded",
            "readiness": readiness,
            "benchmark": None,
            "benchmark_target": benchmark_target,
            "benchmark_thresholds": None,
            "extraction_thresholds": {
                "max_attachment_pending": int(max_attachment_pending),
                "max_ocr_pending": int(max_ocr_pending),
            },
            "failure_codes": [],
            "warning_codes": [],
        }

        if readiness["status"] != "ready":
            report["warning_codes"].append("READINESS_DEGRADED")

        attachment = readiness["derived_text"].get("attachment_text", {})
        ocr = readiness["derived_text"].get("ocr_text", {})
        message_embeddings = readiness["messages"].get("embeddings", {})

        if int(attachment.get("errors", 0)) > 0:
            report["failure_codes"].append("ATTACHMENT_ERRORS_PRESENT")
        if int(ocr.get("errors", 0)) > 0:
            report["failure_codes"].append("OCR_ERRORS_PRESENT")
        if int(attachment.get("pending", 0)) > int(max_attachment_pending):
            report["warning_codes"].append("ATTACHMENT_PENDING_HIGH")
        if int(ocr.get("pending", 0)) > int(max_ocr_pending):
            report["warning_codes"].append("OCR_PENDING_HIGH")

        attachment_issue_reasons = {
            key: value for key, value in dict(attachment.get("issue_reasons") or {}).items() if key
        }
        ocr_issue_reasons = {
            key: value
            for key, value in dict(ocr.get("issue_reasons") or {}).items()
            if key and key != "pdf_has_text_layer"
        }
        if attachment_issue_reasons:
            report["warning_codes"].append("ATTACHMENT_ISSUES_PRESENT")
        if ocr_issue_reasons:
            report["warning_codes"].append("OCR_ISSUES_PRESENT")
        if not bool(message_embeddings.get("configured_model_ready", True)):
            report["warning_codes"].append("MESSAGE_MODEL_COVERAGE_INCOMPLETE")
        attachment_chunk_rollout_started = int(attachment.get("configured_model_chunk_count", 0) or 0) > 0
        ocr_chunk_rollout_started = int(ocr.get("configured_model_chunk_count", 0) or 0) > 0
        if (
            (attachment_chunk_rollout_started and not bool(attachment.get("configured_model_chunk_ready", True)))
            or (ocr_chunk_rollout_started and not bool(ocr.get("configured_model_chunk_ready", True)))
        ):
            report["warning_codes"].append("DERIVED_TEXT_MODEL_COVERAGE_INCOMPLETE")

        if dataset_path:
            dataset = dataset_rows(dataset_path)
            if benchmark_target == "derived_text":
                benchmark = evaluate_derived_text_search(
                    conn,
                    workspace_id=workspace_id,
                    dataset=dataset,
                    mode=mode,
                    limit=limit,
                    model_id=model_id,
                    embedding_provider=self.message_embedding_provider(),
                )
            else:
                benchmark = evaluate_corpus_search(
                    conn,
                    workspace_id=workspace_id,
                    dataset=dataset,
                    mode=mode,
                    limit=limit,
                    model_id=model_id,
                    embedding_provider=self.message_embedding_provider(),
                )
            benchmark["dataset_path"] = dataset_path
            report["benchmark"] = benchmark
            report["benchmark_thresholds"] = {
                "min_hit_at_3": float(min_hit_at_3),
                "min_hit_at_10": float(min_hit_at_10),
                "min_ndcg_at_k": float(min_ndcg_at_k),
                "max_latency_p95_ms": float(max_latency_p95_ms),
            }
            if float(benchmark["hit_at_3"]) < float(min_hit_at_3):
                report["failure_codes"].append("BENCHMARK_HIT_AT_3_LOW")
            if float(benchmark["hit_at_10"]) < float(min_hit_at_10):
                report["failure_codes"].append("BENCHMARK_HIT_AT_10_LOW")
            if float(benchmark["ndcg_at_k"]) < float(min_ndcg_at_k):
                report["failure_codes"].append("BENCHMARK_NDCG_AT_K_LOW")
            if float(benchmark["latency_ms_p95"]) > float(max_latency_p95_ms):
                report["failure_codes"].append("BENCHMARK_LATENCY_P95_HIGH")

            query_reports = list(benchmark.get("query_reports") or [])
            degraded_queries = [
                {
                    "query": row.get("query"),
                    "ndcg_at_k": row.get("ndcg_at_k"),
                    "hit_at_3": row.get("hit_at_3"),
                    "hit_at_10": row.get("hit_at_10"),
                    "latency_ms": row.get("latency_ms"),
                }
                for row in query_reports
                if (
                    float(row.get("ndcg_at_k") or 0.0) < float(min_ndcg_at_k)
                    or not bool(row.get("hit_at_3"))
                    or not bool(row.get("hit_at_10"))
                )
            ]
            if degraded_queries:
                report["warning_codes"].append("BENCHMARK_QUERY_DEGRADATION")
                report["degraded_queries"] = degraded_queries
            else:
                report["degraded_queries"] = []
        else:
            report["degraded_queries"] = []

        if report["failure_codes"]:
            report["status"] = "fail"
        elif report["warning_codes"]:
            report["status"] = "pass_with_warnings"
        return report

    def get_workspace_status(
        self,
        conn,
        *,
        workspace: str | None = None,
        stale_hours: float = 24.0,
        max_zero_msg: int = 0,
        max_stale: int = 0,
        enforce_stale: bool = False,
    ) -> tuple[HealthSummary, list[WorkspaceStatusRow]]:
        if workspace and not get_workspace_by_name(conn, workspace):
            raise ValueError(f"Workspace '{workspace}' not found in DB. Run workspaces sync-config first.")
        stale_seconds = float(stale_hours) * 3600.0
        now_ts = time.time()
        stale_cutoff_ts = now_ts - stale_seconds

        params: list[object] = [stale_cutoff_ts, stale_cutoff_ts]
        where_ws = ""
        if workspace:
            where_ws = " where w.name=?"
            params.append(workspace)

        q = f"""
        with last_msg as (
          select workspace_id, channel_id, max(cast(ts as real)) as max_ts
          from messages
          group by workspace_id, channel_id
        )
        select w.name as workspace,
               case
                 when c.is_im=1 then 'im'
                 when c.is_mpim=1 then 'mpim'
                 when c.is_private=1 then 'private'
                 else 'public'
               end as channel_class,
               count(*) as channels,
               sum(case when lm.max_ts is null then 1 else 0 end) as zero_msg_channels,
               sum(case when lm.max_ts is not null and lm.max_ts < ? then 1 else 0 end) as stale_channels,
               sum(case when lm.max_ts is not null and lm.max_ts < ? then 1 else 0 end) as mirrored_inactive_channels,
               max(lm.max_ts) as class_latest_ts
        from channels c
        join workspaces w on w.id=c.workspace_id
        left join last_msg lm on lm.workspace_id=c.workspace_id and lm.channel_id=c.channel_id
        {where_ws}
        group by w.name, channel_class
        order by w.name, channel_class
        """
        rows = conn.execute(q, tuple(params)).fetchall()

        payload: list[WorkspaceStatusRow] = []
        for ws, cls, channels, zero_msg, stale, mirrored_inactive, latest in rows:
            reasons = []
            if int(zero_msg or 0) > int(max_zero_msg):
                reasons.append(f"zero_msg>{int(max_zero_msg)}")
            if enforce_stale and int(stale or 0) > int(max_stale):
                reasons.append(f"stale>{int(max_stale)}")
            payload.append(
                WorkspaceStatusRow(
                    workspace=ws,
                    channel_class=cls,
                    channels=int(channels or 0),
                    zero_msg_channels=int(zero_msg or 0),
                    stale_channels=int(stale or 0),
                    mirrored_inactive_channels=int(mirrored_inactive or 0),
                    latest_ts=float(latest) if latest else None,
                    health_reasons=reasons,
                )
            )

        unhealthy_rows = [row for row in payload if row.health_reasons]
        summary = HealthSummary(
            status="HEALTHY" if not unhealthy_rows else "UNHEALTHY",
            healthy=not unhealthy_rows,
            max_zero_msg=int(max_zero_msg),
            max_stale=int(max_stale),
            stale_hours=float(stale_hours),
            enforce_stale=bool(enforce_stale),
            unhealthy_rows=len(unhealthy_rows),
        )
        return summary, payload

    def ingest_event(
        self,
        conn,
        *,
        workspace: str,
        event_id: str,
        event_ts: str | None,
        event_type: str | None,
        payload: dict[str, Any],
    ) -> int:
        workspace_id = self.workspace_id(conn, workspace)
        from slack_mirror.core.db import insert_event

        insert_event(conn, workspace_id, event_id, event_ts, event_type, payload, status="pending")
        self._queue_listener_deliveries(
            conn,
            workspace_id=workspace_id,
            event_type=event_type or "unknown",
            payload=payload,
            source_kind="event",
            source_ref=event_id,
        )
        return workspace_id

    def process_pending_events(self, conn, *, workspace: str, limit: int = 100) -> dict[str, int]:
        workspace_id = self.workspace_id(conn, workspace)
        return process_pending_events(conn, workspace_id, limit=limit)

    def _queue_listener_deliveries(
        self,
        conn,
        *,
        workspace_id: int,
        event_type: str,
        payload: dict[str, Any],
        source_kind: str,
        source_ref: str | None = None,
    ) -> int:
        rows = conn.execute(
            """
            SELECT id, name, event_types_json, channel_ids_json, target, delivery_mode, enabled
            FROM listeners
            WHERE workspace_id = ?
            ORDER BY id ASC
            """,
            (workspace_id,),
        ).fetchall()

        payload_json = json.dumps(payload, sort_keys=True)
        channel_id = str((payload.get("event") or {}).get("channel") or payload.get("channel") or "")
        inserted = 0
        with conn:
            for row in rows:
                if int(row["enabled"] or 0) != 1:
                    continue
                event_types = set(json.loads(row["event_types_json"] or "[]"))
                channel_ids = set(json.loads(row["channel_ids_json"] or "[]"))
                if event_types and event_type not in event_types:
                    continue
                if channel_ids and channel_id and channel_id not in channel_ids:
                    continue
                conn.execute(
                    """
                    INSERT INTO listener_deliveries(
                      workspace_id, listener_id, event_type, source_kind, source_ref, payload_json, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (
                        workspace_id,
                        int(row["id"]),
                        event_type,
                        source_kind,
                        source_ref,
                        payload_json,
                    ),
                )
                inserted += 1
        return inserted

    def list_listeners(self, conn, *, workspace: str) -> list[dict[str, Any]]:
        workspace_id = self.workspace_id(conn, workspace)
        rows = conn.execute(
            """
            SELECT id, workspace_id, name, event_types_json, channel_ids_json, target, delivery_mode, enabled,
                   created_at, updated_at
            FROM listeners
            WHERE workspace_id = ?
            ORDER BY id ASC
            """,
            (workspace_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def register_listener(self, conn, *, workspace: str, spec: dict[str, Any]) -> dict[str, Any]:
        workspace_id = self.workspace_id(conn, workspace)
        name = str(spec.get("name") or "").strip()
        if not name:
            raise ValueError("listener spec requires name")
        event_types = spec.get("event_types") or []
        channel_ids = spec.get("channel_ids") or []
        target = spec.get("target")
        delivery_mode = str(spec.get("delivery_mode") or "queue")
        enabled = 1 if spec.get("enabled", True) else 0
        with conn:
            conn.execute(
                """
                INSERT INTO listeners(
                  workspace_id, name, event_types_json, channel_ids_json, target, delivery_mode, enabled
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id, name) DO UPDATE SET
                  event_types_json=excluded.event_types_json,
                  channel_ids_json=excluded.channel_ids_json,
                  target=excluded.target,
                  delivery_mode=excluded.delivery_mode,
                  enabled=excluded.enabled,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (
                    workspace_id,
                    name,
                    json.dumps(list(event_types), sort_keys=True),
                    json.dumps(list(channel_ids), sort_keys=True),
                    target,
                    delivery_mode,
                    enabled,
                ),
            )
        row = conn.execute(
            """
            SELECT id, workspace_id, name, event_types_json, channel_ids_json, target, delivery_mode, enabled,
                   created_at, updated_at
            FROM listeners
            WHERE workspace_id = ? AND name = ?
            """,
            (workspace_id, name),
        ).fetchone()
        if not row:
            raise RuntimeError("failed to register listener")
        return dict(row)

    def unregister_listener(self, conn, *, workspace: str, listener_id: int) -> None:
        workspace_id = self.workspace_id(conn, workspace)
        with conn:
            result = conn.execute(
                "DELETE FROM listeners WHERE workspace_id = ? AND id = ?",
                (workspace_id, listener_id),
            )
        if int(result.rowcount or 0) == 0:
            raise ValueError(f"Listener '{listener_id}' not found in workspace '{workspace}'")

    def get_listener_status(self, conn, *, workspace: str, listener_id: int) -> dict[str, Any]:
        workspace_id = self.workspace_id(conn, workspace)
        row = conn.execute(
            """
            SELECT l.id, l.workspace_id, l.name, l.event_types_json, l.channel_ids_json, l.target, l.delivery_mode,
                   l.enabled, l.created_at, l.updated_at,
                   COUNT(d.id) AS pending_deliveries
            FROM listeners l
            LEFT JOIN listener_deliveries d
              ON d.listener_id = l.id AND d.status = 'pending'
            WHERE l.workspace_id = ? AND l.id = ?
            GROUP BY l.id
            """,
            (workspace_id, listener_id),
        ).fetchone()
        if not row:
            raise ValueError(f"Listener '{listener_id}' not found in workspace '{workspace}'")
        return dict(row)

    def list_listener_deliveries(
        self,
        conn,
        *,
        workspace: str,
        status: str | None = "pending",
        listener_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        workspace_id = self.workspace_id(conn, workspace)
        params: list[Any] = [workspace_id]
        where = ["workspace_id = ?"]
        if status:
            where.append("status = ?")
            params.append(status)
        if listener_id is not None:
            where.append("listener_id = ?")
            params.append(listener_id)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT id, workspace_id, listener_id, event_type, source_kind, source_ref, payload_json, status,
                   attempts, error, delivered_at, created_at, updated_at
            FROM listener_deliveries
            WHERE {' AND '.join(where)}
            ORDER BY id ASC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [dict(row) for row in rows]

    def ack_listener_delivery(self, conn, *, workspace: str, delivery_id: int, status: str = "delivered", error: str | None = None) -> None:
        workspace_id = self.workspace_id(conn, workspace)
        with conn:
            result = conn.execute(
                """
                UPDATE listener_deliveries
                SET status = ?, error = ?, attempts = attempts + 1, delivered_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE workspace_id = ? AND id = ?
                """,
                (status, error, workspace_id, delivery_id),
            )
        if int(result.rowcount or 0) == 0:
            raise ValueError(f"Delivery '{delivery_id}' not found in workspace '{workspace}'")

    def _record_outbound_action(
        self,
        conn,
        *,
        workspace_id: int,
        kind: str,
        channel_id: str,
        text: str,
        thread_ts: str | None,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        idempotency_key = options.get("idempotency_key")
        existing = None
        if idempotency_key:
            existing = conn.execute(
                """
                SELECT id, workspace_id, kind, channel_id, thread_ts, text, options_json, idempotency_key,
                       status, response_json, error, created_at, updated_at
                FROM outbound_actions
                WHERE workspace_id = ? AND kind = ? AND idempotency_key = ?
                """,
                (workspace_id, kind, idempotency_key),
            ).fetchone()
        if existing:
            return dict(existing)

        with conn:
            conn.execute(
                """
                INSERT INTO outbound_actions(
                  workspace_id, kind, channel_id, thread_ts, text, options_json, idempotency_key, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    workspace_id,
                    kind,
                    channel_id,
                    thread_ts,
                    text,
                    json.dumps(options, sort_keys=True),
                    idempotency_key,
                ),
            )
        row = conn.execute(
            """
            SELECT id, workspace_id, kind, channel_id, thread_ts, text, options_json, idempotency_key,
                   status, response_json, error, created_at, updated_at
            FROM outbound_actions
            WHERE workspace_id = ? AND kind = ? AND channel_id = ? AND text = ? AND status = 'pending'
            ORDER BY id DESC
            LIMIT 1
            """,
            (workspace_id, kind, channel_id, text),
        ).fetchone()
        return dict(row)

    def _normalize_outbound_action(self, action: dict[str, Any], *, idempotent_replay: bool) -> dict[str, Any]:
        normalized = dict(action)
        options_json = normalized.get("options_json")
        response_json = normalized.get("response_json")
        normalized["options"] = json.loads(options_json) if options_json else {}
        normalized["response"] = json.loads(response_json) if response_json else None
        normalized["idempotent_replay"] = bool(idempotent_replay)
        normalized["retryable"] = normalized.get("status") in {"pending", "failed"}
        return normalized

    def _existing_outbound_action(
        self,
        conn,
        *,
        workspace_id: int,
        kind: str,
        idempotency_key: str | None,
    ) -> dict[str, Any] | None:
        if not idempotency_key:
            return None
        row = conn.execute(
            """
            SELECT id, workspace_id, kind, channel_id, thread_ts, text, options_json, idempotency_key,
                   status, response_json, error, created_at, updated_at
            FROM outbound_actions
            WHERE workspace_id = ? AND kind = ? AND idempotency_key = ?
            """,
            (workspace_id, kind, idempotency_key),
        ).fetchone()
        return dict(row) if row else None

    def _finish_outbound_action(
        self,
        conn,
        *,
        action_id: int,
        workspace_id: int,
        status: str,
        response: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with conn:
            conn.execute(
                """
                UPDATE outbound_actions
                SET status = ?, response_json = ?, error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE workspace_id = ? AND id = ?
                """,
                (status, json.dumps(response, sort_keys=True) if response is not None else None, error, workspace_id, action_id),
            )

    def send_message(
        self,
        conn,
        *,
        workspace: str,
        channel_ref: str,
        text: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = dict(options or {})
        auth_mode = str(options.pop("auth_mode", "bot"))
        workspace_id = self.workspace_id(conn, workspace)
        existing = self._existing_outbound_action(
            conn,
            workspace_id=workspace_id,
            kind="message",
            idempotency_key=options.get("idempotency_key"),
        )
        if existing:
            return self._normalize_outbound_action(existing, idempotent_replay=True)
        token = self.workspace_token(workspace, auth_mode=auth_mode, purpose="write")
        client = SlackApiClient(token)
        channel_id = self.resolve_outbound_channel(conn, workspace_id=workspace_id, channel_ref=channel_ref, client=client)
        action = self._record_outbound_action(
            conn,
            workspace_id=workspace_id,
            kind="message",
            channel_id=channel_id,
            text=text,
            thread_ts=None,
            options=options,
        )
        if action.get("status") != "pending":
            return self._normalize_outbound_action(action, idempotent_replay=True)
        try:
            response = client.send_message(channel=channel_id, text=text, **options)
            self._finish_outbound_action(
                conn,
                action_id=int(action["id"]),
                workspace_id=workspace_id,
                status="sent",
                response=response,
            )
            self._queue_listener_deliveries(
                conn,
                workspace_id=workspace_id,
                event_type="outbound.message.sent",
                payload={"workspace": workspace, "channel": channel_id, "text": text, "response": response},
                source_kind="outbound",
                source_ref=str(action["id"]),
            )
            action["status"] = "sent"
            action["response_json"] = json.dumps(response, sort_keys=True)
            return self._normalize_outbound_action(action, idempotent_replay=False)
        except Exception as exc:  # noqa: BLE001
            self._finish_outbound_action(
                conn,
                action_id=int(action["id"]),
                workspace_id=workspace_id,
                status="failed",
                error=str(exc),
            )
            raise

    def send_thread_reply(
        self,
        conn,
        *,
        workspace: str,
        channel_ref: str,
        thread_ref: str,
        text: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = dict(options or {})
        auth_mode = str(options.pop("auth_mode", "bot"))
        workspace_id = self.workspace_id(conn, workspace)
        existing = self._existing_outbound_action(
            conn,
            workspace_id=workspace_id,
            kind="thread_reply",
            idempotency_key=options.get("idempotency_key"),
        )
        if existing:
            return self._normalize_outbound_action(existing, idempotent_replay=True)
        token = self.workspace_token(workspace, auth_mode=auth_mode, purpose="write")
        client = SlackApiClient(token)
        channel_id = self.resolve_outbound_channel(conn, workspace_id=workspace_id, channel_ref=channel_ref, client=client)
        action = self._record_outbound_action(
            conn,
            workspace_id=workspace_id,
            kind="thread_reply",
            channel_id=channel_id,
            text=text,
            thread_ts=thread_ref,
            options=options,
        )
        if action.get("status") != "pending":
            return self._normalize_outbound_action(action, idempotent_replay=True)
        try:
            response = client.send_thread_reply(channel=channel_id, thread_ts=thread_ref, text=text, **options)
            self._finish_outbound_action(
                conn,
                action_id=int(action["id"]),
                workspace_id=workspace_id,
                status="sent",
                response=response,
            )
            self._queue_listener_deliveries(
                conn,
                workspace_id=workspace_id,
                event_type="outbound.thread_reply.sent",
                payload={
                    "workspace": workspace,
                    "channel": channel_id,
                    "thread_ts": thread_ref,
                    "text": text,
                    "response": response,
                },
                source_kind="outbound",
                source_ref=str(action["id"]),
            )
            action["status"] = "sent"
            action["response_json"] = json.dumps(response, sort_keys=True)
            return self._normalize_outbound_action(action, idempotent_replay=False)
        except Exception as exc:  # noqa: BLE001
            self._finish_outbound_action(
                conn,
                action_id=int(action["id"]),
                workspace_id=workspace_id,
                status="failed",
                error=str(exc),
            )
            raise


def get_app_service(config_path: str | None = None) -> SlackMirrorAppService:
    return SlackMirrorAppService(config_path=config_path)
