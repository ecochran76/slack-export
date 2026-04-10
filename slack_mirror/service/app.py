from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from slack_mirror.core.config import load_config
from slack_mirror.core.db import apply_migrations, connect, get_workspace_by_name, list_workspaces, upsert_workspace
from slack_mirror.core.slack_api import SlackApiClient
from slack_mirror.service.processor import process_pending_events
from slack_mirror.service.user_env import _build_live_validation_report, default_user_env_paths


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


class SlackMirrorAppService:
    def __init__(self, config_path: str | None = None):
        self.config = load_config(config_path)
        self.db_path = self.config.get("storage", {}).get("db_path", "./data/slack_mirror.db")
        self.migrations_dir = str(Path(__file__).resolve().parents[1] / "core" / "migrations")

    def connect(self):
        conn = connect(self.db_path)
        apply_migrations(conn, self.migrations_dir)
        return conn

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
                    "failure_codes": workspace.failure_codes,
                    "warning_codes": workspace.warning_codes,
                }
                for workspace in report.workspaces
            ],
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
