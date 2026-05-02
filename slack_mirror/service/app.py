from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from html import escape as html_escape
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
from slack_mirror.core.slack_text import render_guest_safe_user_mentions, slack_user_mention_ids, workspace_user_mention_labels
from slack_mirror.exports import (
    build_export_id,
    build_export_manifest,
    delete_export_bundle,
    list_export_manifests,
    rename_export_bundle,
    resolve_export_base_urls,
    resolve_export_root,
    validate_export_id,
)
from slack_mirror.core.slack_api import SlackApiClient
from slack_mirror.search.embeddings import build_embedding_provider, probe_embedding_provider
from slack_mirror.search.eval import dataset_rows, evaluate_corpus_search, evaluate_derived_text_search
from slack_mirror.search.profiles import (
    RetrievalProfile,
    config_with_retrieval_profile,
    list_retrieval_profiles,
    resolve_retrieval_profile,
)
from slack_mirror.search.rerankers import build_reranker_provider, probe_reranker_provider
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


CHILD_EVENT_DESCRIPTORS: tuple[dict[str, Any], ...] = (
    {
        "event_type": "slack.message.observed",
        "eventType": "slack.message.observed",
        "label": "Message observed",
        "summary": "A Slack message is present in mirrored durable state.",
        "privacy": "user",
        "subject_kind": "slack-message",
        "subjectKind": "slack-message",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "message text is preview-limited; native ids stay in source refs",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.thread_reply.observed",
        "eventType": "slack.thread_reply.observed",
        "label": "Thread reply observed",
        "summary": "A Slack thread reply is present in mirrored durable state.",
        "privacy": "user",
        "subject_kind": "slack-message",
        "subjectKind": "slack-message",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "reply text is preview-limited; native ids stay in source refs",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.message.created",
        "eventType": "slack.message.created",
        "label": "Message created",
        "summary": "A Slack message create event was processed from live intake.",
        "privacy": "user",
        "subject_kind": "slack-message",
        "subjectKind": "slack-message",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "message text is preview-limited; native ids stay in source refs",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.thread_reply.created",
        "eventType": "slack.thread_reply.created",
        "label": "Thread reply created",
        "summary": "A Slack thread reply create event was processed from live intake.",
        "privacy": "user",
        "subject_kind": "slack-message",
        "subjectKind": "slack-message",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "reply text is preview-limited; native ids stay in source refs",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.message.changed",
        "eventType": "slack.message.changed",
        "label": "Message changed",
        "summary": "A Slack message edit/update event was processed from live intake.",
        "privacy": "user",
        "subject_kind": "slack-message",
        "subjectKind": "slack-message",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "updated text is preview-limited; native ids stay in source refs",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.message.deleted",
        "eventType": "slack.message.deleted",
        "label": "Message deleted",
        "summary": "A Slack message delete/tombstone event was processed from live intake.",
        "privacy": "user",
        "subject_kind": "slack-message",
        "subjectKind": "slack-message",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "deleted message bodies are not exposed",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.reaction.added",
        "eventType": "slack.reaction.added",
        "label": "Reaction added",
        "summary": "A Slack reaction was added to a mirrored message.",
        "privacy": "user",
        "subject_kind": "slack-message",
        "subjectKind": "slack-message",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "reaction name and native ids are exposed; message body is not included",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.reaction.removed",
        "eventType": "slack.reaction.removed",
        "label": "Reaction removed",
        "summary": "A Slack reaction was removed from a mirrored message.",
        "privacy": "user",
        "subject_kind": "slack-message",
        "subjectKind": "slack-message",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "reaction name and native ids are exposed; message body is not included",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.channel.member_joined",
        "eventType": "slack.channel.member_joined",
        "label": "Channel member joined",
        "summary": "A Slack user joined a channel.",
        "privacy": "user",
        "subject_kind": "slack-channel",
        "subjectKind": "slack-channel",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "channel and user ids are exposed; no message bodies are included",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.channel.member_left",
        "eventType": "slack.channel.member_left",
        "label": "Channel member left",
        "summary": "A Slack user left a channel.",
        "privacy": "user",
        "subject_kind": "slack-channel",
        "subjectKind": "slack-channel",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "channel and user ids are exposed; no message bodies are included",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.user.profile.changed",
        "eventType": "slack.user.profile.changed",
        "label": "User profile changed",
        "summary": "A Slack user profile or status change was processed from live intake.",
        "privacy": "user",
        "subject_kind": "slack-user",
        "subjectKind": "slack-user",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "profile/status display fields may be exposed; raw profile payload is not included",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.outbound.message.sent",
        "eventType": "slack.outbound.message.sent",
        "label": "Outbound message sent",
        "summary": "A Slack Mirror outbound message write completed successfully.",
        "privacy": "user",
        "subject_kind": "slack-message",
        "subjectKind": "slack-message",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "message text is preview-limited; native ids and action ids stay in source refs",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.outbound.thread_reply.sent",
        "eventType": "slack.outbound.thread_reply.sent",
        "label": "Outbound thread reply sent",
        "summary": "A Slack Mirror outbound thread reply write completed successfully.",
        "privacy": "user",
        "subject_kind": "slack-message",
        "subjectKind": "slack-message",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "reply text is preview-limited; native ids and action ids stay in source refs",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.outbound.write.failed",
        "eventType": "slack.outbound.write.failed",
        "label": "Outbound write failed",
        "summary": "A Slack Mirror outbound write failed before Slack confirmed delivery.",
        "privacy": "user",
        "subject_kind": "slack-outbound-action",
        "subjectKind": "slack-outbound-action",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "error text is exposed; message text is preview-limited",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.runtime.live_sync.changed",
        "eventType": "slack.runtime.live_sync.changed",
        "label": "Live sync action processed",
        "summary": "A Slack Mirror tenant live-sync start, restart, or stop action was processed.",
        "privacy": "user",
        "subject_kind": "slack-runtime",
        "subjectKind": "slack-runtime",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "tenant, action, dry-run state, and unit labels may be exposed; secrets are not included",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.sync.initial_sync.requested",
        "eventType": "slack.sync.initial_sync.requested",
        "label": "Initial sync requested",
        "summary": "A Slack Mirror tenant initial history sync/backfill action was requested.",
        "privacy": "user",
        "subject_kind": "slack-sync",
        "subjectKind": "slack-sync",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "tenant, action, options, and command labels may be exposed; secrets are not included",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.file.linked",
        "eventType": "slack.file.linked",
        "label": "File linked",
        "summary": "A Slack file attachment is linked to a mirrored message.",
        "privacy": "user",
        "subject_kind": "slack-file",
        "subjectKind": "slack-file",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "file labels and mimetype are exposed; file contents are not included",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.export.created",
        "eventType": "slack.export.created",
        "label": "Export created",
        "summary": "A managed Slack Mirror export or selected-results report was created.",
        "privacy": "user",
        "subject_kind": "slack-export",
        "subjectKind": "slack-export",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "artifact counts and links are exposed; artifact bodies are read through export routes",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.export.renamed",
        "eventType": "slack.export.renamed",
        "label": "Export renamed",
        "summary": "A managed Slack Mirror export or selected-results report was renamed.",
        "privacy": "user",
        "subject_kind": "slack-export",
        "subjectKind": "slack-export",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "old and new artifact ids are exposed; artifact bodies are read through export routes",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
    {
        "event_type": "slack.export.deleted",
        "eventType": "slack.export.deleted",
        "label": "Export deleted",
        "summary": "A managed Slack Mirror export or selected-results report was deleted.",
        "privacy": "user",
        "subject_kind": "slack-export",
        "subjectKind": "slack-export",
        "payload_stability": "stable",
        "payloadStability": "stable",
        "redaction": "artifact ids and counts may be exposed; deleted artifact bodies are not included",
        "safe_for_roles": ["owner", "user"],
        "safeForRoles": ["owner", "user"],
    },
)


def child_event_descriptors() -> list[dict[str, Any]]:
    return [dict(descriptor) for descriptor in CHILD_EVENT_DESCRIPTORS]


def _rank_movement(baseline_rank: int | None, rank: int | None) -> str:
    if baseline_rank is None and rank is None:
        return "missing_both"
    if baseline_rank is None:
        return "new_hit"
    if rank is None:
        return "lost_hit"
    if rank < baseline_rank:
        return "improved"
    if rank > baseline_rank:
        return "worse"
    return "unchanged"


def _compact_explain(explain: dict[str, Any]) -> dict[str, Any]:
    scores = dict(explain.get("scores") or {})
    ranks = dict(explain.get("ranks") or {})
    weights = dict(explain.get("weights") or {})
    return {
        "mode": explain.get("mode"),
        "source": explain.get("source"),
        "fusion_method": explain.get("fusion_method"),
        "scores": {
            key: scores.get(key)
            for key in ("lexical", "semantic", "hybrid", "rerank")
            if scores.get(key) is not None
        },
        "ranks": {key: ranks.get(key) for key in ("lexical", "semantic") if ranks.get(key) is not None},
        "weights": {
            key: weights.get(key)
            for key in ("lexical", "semantic", "semantic_scale")
            if weights.get(key) is not None
        },
        "rerank_provider": explain.get("rerank_provider"),
    }


def _query_variant_value(query: str, variant: str, authored_variants: Any = None) -> str:
    query = str(query or "")
    name = str(variant or "original").strip().lower()
    if name == "original":
        return query
    if name == "lowercase":
        return query.lower()
    if name == "dehyphen":
        return re.sub(r"\s+", " ", re.sub(r"[-_/]+", " ", query)).strip()
    if name == "alnum":
        return re.sub(r"\s+", " ", re.sub(r"[^0-9A-Za-z]+", " ", query)).strip().lower()
    if name == "dataset":
        if isinstance(authored_variants, list):
            for value in authored_variants:
                if str(value or "").strip():
                    return str(value)
        if isinstance(authored_variants, dict):
            for key in ("default", "primary", "expanded", "normalized"):
                value = authored_variants.get(key)
                if str(value or "").strip():
                    return str(value)
            for value in authored_variants.values():
                if str(value or "").strip():
                    return str(value)
        return query
    if name.startswith("dataset:"):
        key = name.split(":", 1)[1]
        if isinstance(authored_variants, dict):
            value = authored_variants.get(key)
            if str(value or "").strip():
                return str(value)
        return query
    raise ValueError(f"unsupported query variant: {variant}")


def _variant_dataset_rows(rows: list[dict[str, Any]], variant: str) -> list[dict[str, Any]]:
    variant_rows: list[dict[str, Any]] = []
    for row in rows:
        rewritten = dict(row)
        rewritten["query"] = _query_variant_value(
            str(row.get("query") or ""),
            variant,
            row.get("query_variants"),
        )
        variant_rows.append(rewritten)
    return variant_rows


def _variant_definition(variant: str) -> dict[str, Any]:
    name = str(variant or "original").strip()
    descriptions = {
        "original": "benchmark query exactly as authored",
        "lowercase": "lowercase benchmark query",
        "dehyphen": "replace hyphen, underscore, and slash separators with spaces",
        "alnum": "lowercase query with non-alphanumeric runs replaced by spaces",
        "dataset": "use the row's first authored query_variants value when present, otherwise original",
    }
    if name.startswith("dataset:"):
        description = f"use query_variants[{name.split(':', 1)[1]!r}] when present, otherwise original"
    else:
        description = descriptions.get(name, "custom query variant")
    return {"name": name, "description": description}


def _best_query_variant_run(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not runs:
        return None
    return max(
        runs,
        key=lambda run: (
            float(run.get("metrics", {}).get("hit_at_10") or 0.0),
            float(run.get("metrics", {}).get("ndcg_at_k") or 0.0),
            float(run.get("metrics", {}).get("mrr_at_k") or 0.0),
            -float(run.get("metrics", {}).get("latency_ms_p95") or 0.0),
        ),
    )


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


def _truncate_text(value: Any, max_chars: int) -> str:
    text = str(value or "")
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)] + "…"


def _safe_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _slack_ts_to_iso(value: Any) -> str | None:
    try:
        numeric = float(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(numeric, tz=UTC).isoformat().replace("+00:00", "Z")


def _decode_stable_part(value: str) -> str:
    return str(value or "").replace("%7C", "|")


def _normalize_action_target(target: dict[str, Any]) -> dict[str, Any]:
    payload = dict(target or {})
    kind = str(payload.get("kind") or "").strip()
    target_id = str(payload.get("id") or "").strip()
    if target_id and (not kind or kind not in {"message", "derived_text"}):
        parts = [_decode_stable_part(part) for part in target_id.split("|")]
        kind = parts[0] if parts else kind
        payload["kind"] = kind
    if target_id and kind == "message":
        parts = [_decode_stable_part(part) for part in target_id.split("|")]
        if len(parts) >= 4:
            payload.setdefault("workspace", parts[1])
            payload.setdefault("channel_id", parts[2])
            payload.setdefault("ts", parts[3])
    if target_id and kind == "derived_text":
        parts = [_decode_stable_part(part) for part in target_id.split("|")]
        if len(parts) >= 6:
            payload.setdefault("workspace", parts[1])
            payload.setdefault("source_kind", parts[2])
            payload.setdefault("source_id", parts[3])
            payload.setdefault("derivation_kind", parts[4])
            payload.setdefault("extractor", parts[5])
        if len(parts) >= 7 and parts[6].startswith("chunk:"):
            payload.setdefault("chunk_index", parts[6].removeprefix("chunk:"))
    return payload


def _encode_context_cursor(payload: dict[str, Any]) -> str:
    data = json.dumps({"v": 1, **payload}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode_context_cursor(value: str) -> dict[str, Any]:
    token = str(value or "").strip()
    if not token:
        raise ValueError("cursor is required")
    try:
        padded = token + ("=" * (-len(token) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid context cursor") from exc
    if not isinstance(payload, dict) or int(payload.get("v") or 0) != 1:
        raise ValueError("unsupported context cursor")
    return payload


def _encode_event_cursor(recorded_at: str, event_id: str) -> str:
    payload = {"v": 1, "recorded_at": str(recorded_at or ""), "event_id": str(event_id or "")}
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode_event_cursor(value: str | None) -> tuple[str, str] | None:
    token = str(value or "").strip()
    if not token:
        return None
    try:
        padded = token + ("=" * (-len(token) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid event cursor") from exc
    if not isinstance(payload, dict) or int(payload.get("v") or 0) != 1:
        raise ValueError("unsupported event cursor")
    recorded_at = str(payload.get("recorded_at") or "")
    event_id = str(payload.get("event_id") or "")
    if not recorded_at or not event_id:
        raise ValueError("event cursor is missing required fields")
    return recorded_at, event_id


def _event_cursor_for(event: dict[str, Any]) -> str:
    return _encode_event_cursor(str(event.get("recordedAt") or ""), str(event.get("id") or ""))


def _event_filter_values(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for part in str(value or "").split(","):
            token = part.strip()
            if token:
                tokens.add(token.lower())
    return tokens


def _event_value_matches(filters: set[str], candidates: list[Any]) -> bool:
    if not filters:
        return True
    normalized_candidates = {str(candidate or "").strip().lower() for candidate in candidates if str(candidate or "").strip()}
    return bool(filters & normalized_candidates)


def _event_matches_receipts_filters(
    event: dict[str, Any],
    *,
    actor_ref: str | None,
    actor_user_id: str | None,
    channel_ref: str | None,
    channel_id: str | None,
    subject_kind: str | None,
    subject_id: str | None,
) -> bool:
    source_refs = dict(event.get("sourceRefs") or event.get("source_refs") or {})
    payload = dict(event.get("payload") or {})
    actor = dict(event.get("actor") or payload.get("actor") or {})
    subject = dict(event.get("subject") or {})
    actor_filters = _event_filter_values(actor_ref)
    actor_id_filters = _event_filter_values(actor_user_id)
    channel_filters = _event_filter_values(channel_ref)
    channel_id_filters = _event_filter_values(channel_id)
    subject_kind_filters = _event_filter_values(subject_kind)
    subject_id_filters = _event_filter_values(subject_id)
    if not _event_value_matches(
        actor_filters,
        [
            actor.get("label"),
            actor.get("name"),
            actor.get("id"),
            event.get("actorLabel"),
            event.get("actor_label"),
            payload.get("senderLabel"),
            source_refs.get("user_id"),
            source_refs.get("user_name"),
            source_refs.get("user_label"),
        ],
    ):
        return False
    if not _event_value_matches(actor_id_filters, [actor.get("id"), event.get("actorUserId"), event.get("actor_user_id"), source_refs.get("user_id")]):
        return False
    if not _event_value_matches(
        channel_filters,
        [
            source_refs.get("channel_id"),
            source_refs.get("channel_name"),
            payload.get("channelLabel"),
        ],
    ):
        return False
    if not _event_value_matches(channel_id_filters, [source_refs.get("channel_id")]):
        return False
    if not _event_value_matches(subject_kind_filters, [subject.get("kind")]):
        return False
    if not _event_value_matches(subject_id_filters, [subject.get("id")]):
        return False
    return True


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        payload = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _journal_event_title(event_type: str) -> str:
    return {
        "slack.message.created": "Slack message created",
        "slack.thread_reply.created": "Slack thread reply created",
        "slack.message.changed": "Slack message changed",
        "slack.message.deleted": "Slack message deleted",
        "slack.reaction.added": "Slack reaction added",
        "slack.reaction.removed": "Slack reaction removed",
        "slack.channel.member_joined": "Slack channel member joined",
        "slack.channel.member_left": "Slack channel member left",
        "slack.user.profile.changed": "Slack user profile changed",
        "slack.outbound.message.sent": "Slack outbound message sent",
        "slack.outbound.thread_reply.sent": "Slack outbound thread reply sent",
        "slack.outbound.write.failed": "Slack outbound write failed",
        "slack.runtime.live_sync.changed": "Slack live sync action processed",
        "slack.sync.initial_sync.requested": "Slack initial sync requested",
    }.get(event_type, event_type or "Slack event")


def _journal_event_summary(event_type: str, row: dict[str, Any], payload: dict[str, Any]) -> str:
    actor = row.get("actor_label") or row.get("actor_user_id") or "Slack user"
    channel = f"#{row.get('channel_name')}" if row.get("channel_name") else row.get("channel_id")
    reaction = payload.get("reaction")
    if event_type in {"slack.message.created", "slack.thread_reply.created", "slack.message.changed"}:
        text = _truncate_text(payload.get("textPreview"), 120)
        location = f" in {channel}" if channel else ""
        return f"{actor}{location}: {text}" if text else f"{actor}{location}"
    if event_type == "slack.message.deleted":
        return f"{actor} deleted a message" + (f" in {channel}" if channel else "")
    if event_type == "slack.reaction.added":
        return f"{actor} added :{reaction}: reaction" if reaction else f"{actor} added a reaction"
    if event_type == "slack.reaction.removed":
        return f"{actor} removed :{reaction}: reaction" if reaction else f"{actor} removed a reaction"
    if event_type == "slack.channel.member_joined":
        return f"{actor} joined {channel}" if channel else f"{actor} joined a channel"
    if event_type == "slack.channel.member_left":
        return f"{actor} left {channel}" if channel else f"{actor} left a channel"
    if event_type == "slack.user.profile.changed":
        status_text = payload.get("statusText")
        return f"{actor} profile/status changed: {status_text}" if status_text else f"{actor} profile/status changed"
    if event_type in {"slack.outbound.message.sent", "slack.outbound.thread_reply.sent"}:
        text = _truncate_text(payload.get("textPreview"), 120)
        location = f" in {channel}" if channel else ""
        return f"Outbound write sent{location}: {text}" if text else f"Outbound write sent{location}"
    if event_type == "slack.outbound.write.failed":
        return f"Outbound write failed: {_truncate_text(payload.get('error'), 120)}"
    if event_type == "slack.runtime.live_sync.changed":
        action = payload.get("action") or "live-sync"
        status = payload.get("status") or "processed"
        return f"Live sync {action} {status}"
    if event_type == "slack.sync.initial_sync.requested":
        status = payload.get("status") or "requested"
        return f"Initial sync {status}"
    return _journal_event_title(event_type)


def _sqlite_timestamp_to_iso(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "T" in text:
        return text if text.endswith("Z") or "+" in text else f"{text}Z"
    try:
        return datetime.fromisoformat(text.replace(" ", "T")).replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
    except ValueError:
        return text


def _project_context_message(
    row: Any,
    *,
    workspace: str,
    relation: str,
    selected: bool,
    include_text: bool,
    max_text_chars: int,
    mention_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = dict(row)
    result = {
        "kind": "message",
        "workspace": workspace,
        "channel_id": payload.get("channel_id"),
        "channel_name": payload.get("channel_name"),
        "ts": payload.get("ts"),
        "thread_ts": payload.get("thread_ts"),
        "user_id": payload.get("user_id"),
        "user_label": payload.get("user_label"),
        "subtype": payload.get("subtype"),
        "edited_ts": payload.get("edited_ts"),
        "deleted": payload.get("deleted"),
        "relation": relation,
        "selected": bool(selected),
    }
    if include_text:
        raw_text = _truncate_text(payload.get("text"), max_text_chars)
        guest_safe_text = render_guest_safe_user_mentions(raw_text, mention_labels or {})
        result["text"] = guest_safe_text
        if guest_safe_text != raw_text:
            result["raw_text"] = raw_text
            result["text_rendering"] = {
                "kind": "slack_mrkdwn_guest_safe",
                "mentions": "user_display_labels",
                "emoji": "common_unicode_aliases",
                "unresolved_user_placeholder": "@unresolved-slack-user",
            }
    return result


def _project_context_chunk(
    row: dict[str, Any],
    *,
    selected: bool,
    include_text: bool,
    max_text_chars: int,
) -> dict[str, Any]:
    payload = dict(row)
    result = {
        "kind": "derived_text_chunk",
        "chunk_index": payload.get("chunk_index"),
        "start_offset": payload.get("start_offset"),
        "end_offset": payload.get("end_offset"),
        "selected": bool(selected),
    }
    if include_text:
        result["text"] = _truncate_text(payload.get("text"), max_text_chars)
    return result


def _select_context_chunks(
    chunks: list[dict[str, Any]],
    *,
    selected_chunk: int | None,
    before: int,
    after: int,
    include_text: bool,
    max_text_chars: int,
) -> list[dict[str, Any]]:
    if not chunks:
        return []
    ordered = sorted(chunks, key=lambda row: int(row.get("chunk_index") or 0))
    indexes = [int(row.get("chunk_index") or 0) for row in ordered]
    if selected_chunk is None or selected_chunk not in indexes:
        window = ordered[: max(1, before + after + 1)]
        return [
            _project_context_chunk(row, selected=index == 0, include_text=include_text, max_text_chars=max_text_chars)
            for index, row in enumerate(window)
        ]
    selected_position = indexes.index(selected_chunk)
    start = max(0, selected_position - before)
    end = min(len(ordered), selected_position + after + 1)
    return [
        _project_context_chunk(
            row,
            selected=int(row.get("chunk_index") or 0) == selected_chunk,
            include_text=include_text,
            max_text_chars=max_text_chars,
        )
        for row in ordered[start:end]
    ]


class SlackMirrorAppService:
    def __init__(self, config_path: str | None = None):
        self.config = load_config(config_path)
        self.db_path = self.config.get("storage", {}).get("db_path", "./data/slack_mirror.db")
        self.migrations_dir = str(Path(__file__).resolve().parents[1] / "core" / "migrations")
        self._message_embedding_provider = None
        self._reranker_provider = None

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

    def reranker_provider(self):
        if self._reranker_provider is None:
            self._reranker_provider = build_reranker_provider(self.config.data)
        return self._reranker_provider

    def reranker_probe(
        self,
        *,
        model_id: str | None = None,
        smoke_query: str | None = None,
        smoke_documents: list[str] | None = None,
    ) -> dict[str, Any]:
        return probe_reranker_provider(
            self.config.data,
            model_id=model_id,
            smoke_query=smoke_query,
            smoke_documents=smoke_documents,
        )

    def retrieval_profiles(self) -> list[dict[str, Any]]:
        return [profile.to_dict() for profile in list_retrieval_profiles(self.config.data)]

    def retrieval_profile(self, name: str | None) -> RetrievalProfile:
        return resolve_retrieval_profile(self.config.data, name)

    def config_for_retrieval_profile(self, profile: RetrievalProfile) -> dict[str, Any]:
        return config_with_retrieval_profile(self.config.data, profile)

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

    def create_selected_result_export(
        self,
        conn,
        *,
        targets: list[dict[str, Any]],
        before: int = 2,
        after: int = 2,
        include_text: bool = True,
        max_text_chars: int = 4000,
        audience: str = "local",
        export_id: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        context_pack = self.build_search_context_pack(
            conn,
            targets=targets,
            before=before,
            after=after,
            include_text=include_text,
            max_text_chars=max_text_chars,
        )
        target_workspaces = sorted(
            {
                str(target.get("workspace") or "").strip()
                for target in targets
                if str(target.get("workspace") or "").strip()
            }
        )
        workspace_label = target_workspaces[0] if len(target_workspaces) == 1 else "multi"
        export_title = str(title or "Selected search results").strip() or "Selected search results"
        if export_id:
            resolved_export_id = validate_export_id(export_id)
        else:
            resolved_export_id = build_export_id(
                "selected-results",
                workspace=workspace_label,
                descriptor=export_title,
                seed_extra={
                    "targets": targets,
                    "before": before,
                    "after": after,
                    "include_text": include_text,
                    "max_text_chars": max_text_chars,
                    "generated_at": time.time_ns(),
                },
            )

        export_root = resolve_export_root(self.config)
        bundle_dir = export_root / resolved_export_id
        if bundle_dir.exists():
            raise FileExistsError(f"export bundle already exists: {resolved_export_id}")
        bundle_dir.mkdir(parents=True, exist_ok=False)

        generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        payload = {
            "schema_version": 1,
            "kind": "selected-results",
            "generated_at": generated_at,
            "producer": {"name": "slack-mirror"},
            "export_id": resolved_export_id,
            "title": export_title,
            "workspace": workspace_label,
            "workspaces": target_workspaces,
            "source": {
                "targets": targets,
                "context_policy": context_pack.get("context_policy", {}),
            },
            "item_count": context_pack.get("item_count", 0),
            "resolved_count": context_pack.get("resolved_count", 0),
            "unresolved_count": context_pack.get("unresolved_count", 0),
            "events": self._selected_result_events_projection(context_pack),
            "context_pack": context_pack,
        }
        (bundle_dir / "selected-results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        index_html = self._selected_result_export_index_html(payload)
        (bundle_dir / "index.html").write_text(index_html, encoding="utf-8")
        manifest = build_export_manifest(
            bundle_dir,
            export_id=resolved_export_id,
            base_urls=resolve_export_base_urls(self.config),
            default_audience=audience,
        )
        (bundle_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    @staticmethod
    def _selected_result_events_projection(context_pack: dict[str, Any]) -> list[dict[str, Any]]:
        items = context_pack.get("items") if isinstance(context_pack.get("items"), list) else []
        events: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("resolved"):
                continue
            item_index = _safe_int_or_none(item.get("index")) or len(events) + 1
            if item.get("kind") == "message":
                context = item.get("context") if isinstance(item.get("context"), list) else []
                for context_index, row in enumerate(context, start=1):
                    if isinstance(row, dict):
                        events.append(
                            SlackMirrorAppService._selected_result_message_event(
                                item,
                                row,
                                item_index,
                                context_index,
                            )
                        )
            elif item.get("kind") == "derived_text":
                chunks = item.get("context_chunks") if isinstance(item.get("context_chunks"), list) else []
                for context_index, chunk in enumerate(chunks, start=1):
                    if isinstance(chunk, dict):
                        events.append(
                            SlackMirrorAppService._selected_result_derived_text_event(
                                item,
                                chunk,
                                item_index,
                                context_index,
                            )
                        )
                linked_messages = item.get("linked_messages") if isinstance(item.get("linked_messages"), list) else []
                for context_index, row in enumerate(linked_messages, start=1):
                    if isinstance(row, dict):
                        events.append(
                            SlackMirrorAppService._selected_result_message_event(
                                item,
                                row,
                                item_index,
                                context_index,
                            )
                        )
        return events

    @staticmethod
    def _selected_result_message_event(
        item: dict[str, Any],
        row: dict[str, Any],
        item_index: int,
        context_index: int,
    ) -> dict[str, Any]:
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        workspace = str(row.get("workspace") or item.get("workspace") or target.get("workspace") or "")
        workspace_id = item.get("workspace_id")
        channel_id = str(row.get("channel_id") or target.get("channel_id") or "")
        channel_name = str(row.get("channel_name") or "")
        ts = str(row.get("ts") or target.get("ts") or "")
        thread_ts = str(row.get("thread_ts") or "") or None
        relation = str(row.get("relation") or ("hit" if row.get("selected") else "occurrence"))
        user_id = row.get("user_id")
        user_label = row.get("user_label")
        timestamp = _slack_ts_to_iso(ts)
        event = {
            "schema_version": 1,
            "id": f"slack-message|{workspace}|{channel_id}|{ts}|{relation}|{item_index}|{context_index}",
            "platform": "slack",
            "kind": "message",
            "relation": relation,
            "selected": bool(row.get("selected")),
            "exact_hit": bool(row.get("selected") or relation == "hit"),
            "source": {
                "kind": "workspace",
                "id": str(workspace_id) if workspace_id is not None else None,
                "name": workspace or None,
                "native": {"workspace": workspace or None, "workspace_id": workspace_id},
            },
            "conversation": {
                "kind": "slack_channel",
                "id": channel_id or None,
                "name": channel_name or None,
                "native": {"channel_id": channel_id or None, "channel_name": channel_name or None},
            },
            "thread": {
                "id": f"{channel_id}:{thread_ts or ts}" if channel_id and (thread_ts or ts) else None,
                "root_ts": thread_ts or ts or None,
                "native": {"thread_ts": thread_ts, "ts": ts or None},
            },
            "timestamp": timestamp,
            "participants": [
                {
                    "role": "sender",
                    "id": user_id,
                    "display_name": user_label,
                    "native": {"user_id": user_id},
                }
            ]
            if user_id or user_label
            else [],
            "subject": f"#{channel_name}" if channel_name else channel_id or None,
            "attachments": [],
            "derived_text_refs": [],
            "source_refs": {
                "workspace": workspace or None,
                "workspace_id": workspace_id,
                "channel_id": channel_id or None,
                "channel_name": channel_name or None,
                "ts": ts or None,
                "thread_ts": thread_ts,
                "subtype": row.get("subtype"),
                "edited_ts": row.get("edited_ts"),
                "deleted": row.get("deleted"),
            },
            "action_target": target,
            "warnings": [] if timestamp else ["slack_ts_requires_provider_specific_timestamp_parsing"],
        }
        if "text" in row:
            event["text"] = row.get("text")
        if "raw_text" in row:
            event["raw_text"] = row.get("raw_text")
        if "text_rendering" in row:
            event["text_rendering"] = row.get("text_rendering")
        return event

    @staticmethod
    def _selected_result_derived_text_event(
        item: dict[str, Any],
        chunk: dict[str, Any],
        item_index: int,
        context_index: int,
    ) -> dict[str, Any]:
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        derived = item.get("derived_text") if isinstance(item.get("derived_text"), dict) else {}
        workspace = str(item.get("workspace") or target.get("workspace") or "")
        workspace_id = item.get("workspace_id")
        source_kind = str(source.get("kind") or target.get("source_kind") or "")
        source_id = str(source.get("id") or target.get("source_id") or "")
        source_label = str(source.get("label") or source_id or "")
        chunk_index = chunk.get("chunk_index")
        relation = "hit" if chunk.get("selected") else "occurrence"
        derived_ref = {
            "source_kind": source_kind or None,
            "source_id": source_id or None,
            "source_label": source_label or None,
            "derivation_kind": derived.get("derivation_kind"),
            "extractor": derived.get("extractor"),
            "media_type": derived.get("media_type"),
            "language_code": derived.get("language_code"),
            "confidence": derived.get("confidence"),
            "chunk_index": chunk_index,
            "start_offset": chunk.get("start_offset"),
            "end_offset": chunk.get("end_offset"),
        }
        event = {
            "schema_version": 1,
            "id": f"slack-derived-text|{workspace}|{source_kind}|{source_id}|chunk:{chunk_index}|{relation}|{item_index}|{context_index}",
            "platform": "slack",
            "kind": "derived_text_chunk",
            "relation": relation,
            "selected": bool(chunk.get("selected")),
            "exact_hit": bool(chunk.get("selected")),
            "source": {
                "kind": "workspace",
                "id": str(workspace_id) if workspace_id is not None else None,
                "name": workspace or None,
                "native": {"workspace": workspace or None, "workspace_id": workspace_id},
            },
            "conversation": None,
            "thread": None,
            "timestamp": None,
            "participants": [],
            "subject": source_label or None,
            "attachments": [
                {
                    "kind": "slack_file",
                    "id": source_id,
                    "filename": source_label or None,
                    "native": {"file_id": source_id},
                }
            ]
            if source_kind == "file" and source_id
            else [],
            "derived_text_refs": [derived_ref],
            "source_refs": {
                "workspace": workspace or None,
                "workspace_id": workspace_id,
                "source_kind": source_kind or None,
                "source_id": source_id or None,
                "derived_text_id": derived.get("id"),
            },
            "action_target": target,
            "warnings": [],
        }
        if "text" in chunk:
            event["text"] = chunk.get("text")
        return event

    @staticmethod
    def _selected_result_export_index_html(payload: dict[str, Any]) -> str:
        title = html_escape(str(payload.get("title") or "Selected search results"))
        export_id = html_escape(str(payload.get("export_id") or ""))
        item_count = int(payload.get("item_count") or 0)
        resolved_count = int(payload.get("resolved_count") or 0)
        unresolved_count = int(payload.get("unresolved_count") or 0)
        generated_at = html_escape(str(payload.get("generated_at") or ""))
        context_pack = payload.get("context_pack") if isinstance(payload.get("context_pack"), dict) else {}
        context_policy = context_pack.get("context_policy") if isinstance(context_pack.get("context_policy"), dict) else {}
        include_text = bool(context_policy.get("include_text", True))
        items = context_pack.get("items") if isinstance(context_pack.get("items"), list) else []
        item_cards = "\n".join(SlackMirrorAppService._selected_result_report_item_html(item) for item in items)
        if not item_cards:
            item_cards = "<section class=\"empty\">No selected result items were stored in this bundle.</section>"
        policy_bits = [
            f"before={html_escape(str(context_policy.get('before', 0)))}",
            f"after={html_escape(str(context_policy.get('after', 0)))}",
            f"text={'included' if include_text else 'omitted'}",
            f"max_text_chars={html_escape(str(context_policy.get('max_text_chars', 0)))}",
        ]
        return (
            "<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{title}</title>"
            "<style>:root{--ink:#152033;--muted:#66717f;--line:#ded4c4;--paper:#fffdf8;--field:#fbf6ec;--accent:#8a3b12;--good:#236245;--bad:#9d2c2c}"
            "body{font-family:ui-sans-serif,system-ui,sans-serif;margin:0;background:radial-gradient(circle at top left,#efe3cf,#f8f3ea 38%,#eef1ec);color:var(--ink)}"
            "main{max-width:1120px;margin:0 auto;padding:44px 24px 72px}.hero{padding:30px;background:rgba(255,253,248,.92);border:1px solid var(--line);border-radius:28px;box-shadow:0 24px 70px rgba(21,32,51,.14)}"
            ".report-toolbar{position:sticky;top:0;z-index:10;margin:-44px auto 22px;padding:12px 24px;background:rgba(248,243,234,.9);backdrop-filter:blur(10px);border-bottom:1px solid rgba(222,212,196,.8)}"
            ".toolbar-inner{max-width:1120px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:12px}.toolbar-title{font-size:13px;font-weight:800;color:#4e5968;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.toolbar-actions{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end}"
            "h1{margin:0 0 10px;font-size:clamp(30px,5vw,56px);line-height:.98;letter-spacing:-.04em}.meta{color:var(--muted);margin:0 0 22px;line-height:1.6}.policy{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}"
            ".chip{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:999px;background:#fffaf0;color:#5c5147;padding:6px 10px;font-size:12px;font-weight:700}.chip.good{color:var(--good)}.chip.bad{color:var(--bad)}"
            ".stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:24px 0}.stat{padding:16px;border:1px solid #e6ddcf;border-radius:18px;background:var(--field)}"
            ".num{font-size:34px;font-weight:800}.label{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#6d6257}.items{display:grid;gap:18px;margin-top:22px}"
            ".item{background:rgba(255,253,248,.94);border:1px solid var(--line);border-radius:24px;padding:20px;box-shadow:0 12px 36px rgba(21,32,51,.08)}.item-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px}"
            ".item h2{margin:0;font-size:22px;letter-spacing:-.02em}.target{color:var(--muted);font-size:13px;line-height:1.5}.section-title{margin:18px 0 8px;color:#4c5664;text-transform:uppercase;letter-spacing:.08em;font-size:12px;font-weight:800}"
            ".item-actions{display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-end;gap:8px}.copy-btn{border:1px solid #d7c8b6;border-radius:999px;background:#fffaf0;color:#593b25;padding:7px 10px;font-size:12px;font-weight:800;cursor:pointer}.copy-btn:focus{outline:2px solid #b87b45;outline-offset:2px}.copy-btn.copied{background:#e8f2ed;color:var(--good)}"
            ".status-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.fold{border:1px solid #e6ddcf;border-radius:18px;background:rgba(251,246,236,.65);padding:0;margin-top:14px}.fold>summary{cursor:pointer;padding:12px 14px;font-weight:900;color:#4c5664;text-transform:uppercase;letter-spacing:.07em;font-size:12px}.fold-body{padding:0 14px 14px}"
            ".timeline{display:grid;gap:10px}.message,.chunk{border:1px solid #e9dfd0;border-radius:16px;background:#fffaf3;padding:12px}.message.hit,.chunk.hit{border-color:#b87b45;background:#fff2df}.message.linked{border-style:dashed}.row{display:flex;gap:8px;flex-wrap:wrap;color:var(--muted);font-size:12px;margin-bottom:8px}"
            ".text{white-space:pre-wrap;margin:0;color:#1c2838;font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.omitted{margin:0;color:var(--muted);font-style:italic}.empty{padding:20px;border:1px dashed var(--line);border-radius:18px;background:#fffaf3;color:var(--muted)}"
            "a{color:var(--accent);font-weight:800}@media(max-width:720px){main{padding:0}.report-toolbar{margin:0;padding:10px 14px}.toolbar-inner{align-items:flex-start;flex-direction:column}.hero,.item{border-radius:0;border-left:0;border-right:0}.stats{grid-template-columns:1fr}.item-head{display:block}.item-actions{justify-content:flex-start;margin-top:10px}}"
            "@media print{body{background:#fff}.report-toolbar,.copy-btn{display:none}.hero,.item,.message,.chunk,.stat{box-shadow:none;break-inside:avoid}.fold{border:0;background:#fff}.fold>summary{list-style:none;padding-left:0}.fold-body{padding:0}.items{gap:12px}main{padding:0}}"
            "</style></head>"
            "<body><div class=\"report-toolbar\"><div class=\"toolbar-inner\">"
            f"<div class=\"toolbar-title\">{title} · {item_count} selected · {resolved_count} resolved · {unresolved_count} unresolved</div>"
            "<div class=\"toolbar-actions\"><button class=\"copy-btn\" type=\"button\" onclick=\"window.print()\">Print / Save PDF</button>"
            "<button class=\"copy-btn\" type=\"button\" data-copy-fragment=\"\">Copy report link</button></div></div></div>"
            f"<main><section class=\"hero\"><h1>{title}</h1><p class=\"meta\">Export <code>{export_id}</code><br>Generated {generated_at}</p>"
            "<div class=\"stats\">"
            f"<div class=\"stat\"><div class=\"num\">{item_count}</div><div class=\"label\">Selected</div></div>"
            f"<div class=\"stat\"><div class=\"num\">{resolved_count}</div><div class=\"label\">Resolved</div></div>"
            f"<div class=\"stat\"><div class=\"num\">{unresolved_count}</div><div class=\"label\">Unresolved</div></div>"
            "</div>"
            f"<div class=\"policy\">{''.join(f'<span class=\"chip\">{bit}</span>' for bit in policy_bits)}</div>"
            "<p class=\"meta\">This report is rendered from the neutral <a href=\"selected-results.json\">selected-results.json</a> artifact.</p></section>"
            f"<section class=\"items\">{item_cards}</section></main>"
            "<script>document.addEventListener('click',async(event)=>{const button=event.target.closest('[data-copy-text],[data-copy-fragment]');if(!button)return;const text=button.dataset.copyText!==undefined?button.dataset.copyText:window.location.href.split('#')[0]+(button.dataset.copyFragment||'');try{await navigator.clipboard.writeText(text);button.classList.add('copied');const old=button.textContent;button.textContent='Copied';window.setTimeout(()=>{button.textContent=old;button.classList.remove('copied');},1200);}catch(error){button.textContent='Copy failed';}});</script>"
            "</body></html>"
        )

    @staticmethod
    def _selected_result_report_item_html(item: dict[str, Any]) -> str:
        index = html_escape(str(item.get("index") or "?"))
        kind = html_escape(str(item.get("kind") or "unknown"))
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        target_label = html_escape(
            str(target.get("selection_label") or target.get("id") or target.get("source_id") or target.get("ts") or "unlabeled")
        )
        resolved = bool(item.get("resolved"))
        status_class = "good" if resolved else "bad"
        status_label = "resolved" if resolved else html_escape(str(item.get("reason") or "unresolved"))
        anchor = f"selected-result-{index}"
        target_json = json.dumps(target, sort_keys=True, separators=(",", ":"))
        target_json_attr = html_escape(target_json, quote=True)
        if kind == "message":
            body = SlackMirrorAppService._selected_result_message_item_html(item)
        elif kind == "derived_text":
            body = SlackMirrorAppService._selected_result_derived_item_html(item)
        else:
            body = f"<p class=\"omitted\">Unsupported selected-result kind: {kind}</p>"
        return (
            f"<article class=\"item\" id=\"{anchor}\">"
            "<div class=\"item-head\">"
            f"<div><h2>#{index} {kind}</h2><div class=\"target\">{target_label}</div>"
            f"<div class=\"status-row\"><span class=\"chip {status_class}\">{status_label}</span><span class=\"chip\">type: {kind}</span></div></div>"
            "<div class=\"item-actions\">"
            f"<a class=\"chip\" href=\"#{anchor}\">permalink</a>"
            f"<button class=\"copy-btn\" type=\"button\" data-copy-fragment=\"#{anchor}\">Copy link</button>"
            f"<button class=\"copy-btn\" type=\"button\" data-copy-text=\"{target_json_attr}\">Copy target JSON</button>"
            "</div>"
            "</div>"
            f"{body}</article>"
        )

    @staticmethod
    def _selected_result_message_item_html(item: dict[str, Any]) -> str:
        conversation = item.get("conversation") if isinstance(item.get("conversation"), dict) else {}
        context = item.get("context") if isinstance(item.get("context"), list) else []
        heading = html_escape(str(conversation.get("channel_name") or conversation.get("channel_id") or "conversation"))
        if not item.get("resolved"):
            return f"<p class=\"omitted\">Message target was not resolved: {html_escape(str(item.get('reason') or 'not_found'))}</p>"
        cards = "\n".join(SlackMirrorAppService._selected_result_message_card_html(row) for row in context)
        if not cards:
            cards = "<p class=\"omitted\">No message context was stored.</p>"
        return (
            f"<details class=\"fold\" open><summary>Message context: {heading}</summary>"
            f"<div class=\"fold-body\"><div class=\"timeline\">{cards}</div></div></details>"
        )

    @staticmethod
    def _selected_result_derived_item_html(item: dict[str, Any]) -> str:
        if not item.get("resolved"):
            return f"<p class=\"omitted\">Derived-text target was not resolved: {html_escape(str(item.get('reason') or 'not_found'))}</p>"
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        derived = item.get("derived_text") if isinstance(item.get("derived_text"), dict) else {}
        chunks = item.get("context_chunks") if isinstance(item.get("context_chunks"), list) else []
        linked_messages = item.get("linked_messages") if isinstance(item.get("linked_messages"), list) else []
        source_label = html_escape(str(source.get("label") or source.get("id") or "source"))
        derived_bits = [
            html_escape(str(value))
            for value in [
                source.get("kind"),
                derived.get("derivation_kind"),
                derived.get("extractor"),
                derived.get("media_type"),
            ]
            if value
        ]
        chunk_cards = "\n".join(SlackMirrorAppService._selected_result_chunk_card_html(chunk) for chunk in chunks)
        if not chunk_cards:
            chunk_cards = "<p class=\"omitted\">No derived-text chunks were stored.</p>"
        linked_cards = "\n".join(SlackMirrorAppService._selected_result_message_card_html(row) for row in linked_messages)
        linked_section = (
            f"<details class=\"fold\"><summary>Linked Slack messages</summary><div class=\"fold-body\"><div class=\"timeline\">{linked_cards}</div></div></details>"
            if linked_cards
            else "<p class=\"omitted\">No linked Slack messages were stored for this source.</p>"
        )
        return (
            f"<div class=\"section-title\">Derived text: {source_label}</div>"
            f"<div class=\"target\">{' / '.join(derived_bits)}</div>"
            f"<details class=\"fold\" open><summary>Chunk context</summary><div class=\"fold-body\"><div class=\"timeline\">{chunk_cards}</div></div></details>"
            f"{linked_section}"
        )

    @staticmethod
    def _selected_result_message_card_html(row: dict[str, Any]) -> str:
        selected = bool(row.get("selected"))
        relation = html_escape(str(row.get("relation") or ("hit" if selected else "context")))
        class_names = ["message"]
        if selected or relation == "hit":
            class_names.append("hit")
        if relation == "linked":
            class_names.append("linked")
        label_bits = [
            html_escape(str(value))
            for value in [relation, row.get("workspace"), row.get("channel_name") or row.get("channel_id"), row.get("ts"), row.get("user_label") or row.get("user_id")]
            if value
        ]
        return (
            f"<div class=\"{' '.join(class_names)}\"><div class=\"row\">"
            + "".join(f"<span class=\"chip\">{bit}</span>" for bit in label_bits)
            + "</div>"
            + SlackMirrorAppService._selected_result_text_html(row)
            + "</div>"
        )

    @staticmethod
    def _selected_result_chunk_card_html(row: dict[str, Any]) -> str:
        selected = bool(row.get("selected"))
        class_names = "chunk hit" if selected else "chunk"
        label_bits = [
            f"chunk {html_escape(str(row.get('chunk_index')))}",
            f"offset {html_escape(str(row.get('start_offset')))}-{html_escape(str(row.get('end_offset')))}",
        ]
        return (
            f"<div class=\"{class_names}\"><div class=\"row\">"
            + "".join(f"<span class=\"chip\">{bit}</span>" for bit in label_bits)
            + "</div>"
            + SlackMirrorAppService._selected_result_text_html(row)
            + "</div>"
        )

    @staticmethod
    def _selected_result_text_html(row: dict[str, Any]) -> str:
        if "text" not in row:
            return "<p class=\"omitted\">Text omitted in this export.</p>"
        text = str(row.get("text") or "").strip()
        if not text:
            return "<p class=\"omitted\">No text stored for this item.</p>"
        return f"<pre class=\"text\">{html_escape(text)}</pre>"

    def rename_export(self, *, export_id: str, new_export_id: str, audience: str = "local") -> dict[str, Any]:
        manifest = rename_export_bundle(
            resolve_export_root(self.config),
            export_id=export_id,
            new_export_id=new_export_id,
            base_urls=resolve_export_base_urls(self.config),
            default_audience=audience,
        )
        if export_id != new_export_id:
            self._append_export_lifecycle_event(
                event_type="slack.export.renamed",
                export_id=str(new_export_id),
                workspace=str(manifest.get("workspace") or ""),
                manifest=manifest,
                payload={"oldExportId": export_id, "newExportId": new_export_id},
            )
        return manifest

    def delete_export(self, *, export_id: str) -> bool:
        export_root = resolve_export_root(self.config)
        manifest: dict[str, Any] = {}
        bundle_dir = export_root / export_id
        if bundle_dir.exists() and bundle_dir.is_dir():
            try:
                manifest = build_export_manifest(
                    bundle_dir,
                    export_id=export_id,
                    base_urls=resolve_export_base_urls(self.config),
                    default_audience="local",
                )
            except Exception:  # noqa: BLE001 - deletion should still be attempted.
                manifest = {"export_id": export_id}
        deleted = delete_export_bundle(export_root, export_id)
        if deleted:
            self._append_export_lifecycle_event(
                event_type="slack.export.deleted",
                export_id=str(export_id),
                workspace=str(manifest.get("workspace") or ""),
                manifest=manifest or {"export_id": export_id},
                payload={"exportId": export_id},
            )
        return deleted

    def build_search_context_pack(
        self,
        conn,
        *,
        targets: list[dict[str, Any]],
        before: int = 2,
        after: int = 2,
        include_text: bool = True,
        max_text_chars: int = 4000,
    ) -> dict[str, Any]:
        before_count = max(0, min(int(before), 50))
        after_count = max(0, min(int(after), 50))
        text_limit = max(0, int(max_text_chars))
        items: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        for index, target in enumerate(targets, start=1):
            normalized = _normalize_action_target(target)
            kind = normalized.get("kind")
            if kind == "message":
                item = self._message_context_pack_item(
                    conn,
                    target=normalized,
                    before=before_count,
                    after=after_count,
                    include_text=include_text,
                    max_text_chars=text_limit,
                )
            elif kind == "derived_text":
                item = self._derived_text_context_pack_item(
                    conn,
                    target=normalized,
                    before=before_count,
                    after=after_count,
                    include_text=include_text,
                    max_text_chars=text_limit,
                )
            else:
                item = {
                    "index": index,
                    "kind": kind or "unknown",
                    "target": normalized,
                    "resolved": False,
                    "reason": "unsupported_target_kind",
                }
            item["index"] = index
            items.append(item)
            if not item.get("resolved"):
                unresolved.append(
                    {
                        "index": index,
                        "kind": item.get("kind"),
                        "target": normalized,
                        "reason": item.get("reason", "not_found"),
                    }
                )
        return {
            "schema_version": 1,
            "kind": "search_context_pack",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "context_policy": {
                "before": before_count,
                "after": after_count,
                "include_text": bool(include_text),
                "max_text_chars": text_limit,
            },
            "item_count": len(items),
            "resolved_count": len([item for item in items if item.get("resolved")]),
            "unresolved_count": len(unresolved),
            "items": items,
            "unresolved": unresolved,
        }

    def build_context_window(
        self,
        conn,
        *,
        result_id: str,
        direction: str = "around",
        cursor: str | None = None,
        limit: int = 25,
        include_text: bool = True,
        max_text_chars: int = 4000,
    ) -> dict[str, Any]:
        normalized_direction = str(direction or "around").strip().lower()
        if normalized_direction not in {"around", "before", "after"}:
            raise ValueError("direction must be one of around, before, or after")

        item_limit = max(1, min(int(limit), 100))
        text_limit = max(0, int(max_text_chars))
        target = _normalize_action_target({"id": result_id})
        if target.get("kind") != "message":
            raise ValueError("context windows currently require a message result_id")
        workspace = str(target.get("workspace") or "").strip()
        channel_id = str(target.get("channel_id") or "").strip()
        selected_ts = str(target.get("ts") or "").strip()
        if not workspace or not channel_id or not selected_ts:
            raise ValueError("result_id must identify a Slack message")

        workspace_id = self.workspace_id(conn, workspace)
        hit = self._message_context_row(conn, workspace=workspace, workspace_id=workspace_id, channel_id=channel_id, ts=selected_ts)
        if hit is None:
            raise ValueError("message not found in workspace")

        thread_root = str(hit.get("thread_ts") or "").strip()
        if not thread_root:
            reply_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM messages
                WHERE workspace_id = ? AND channel_id = ? AND thread_ts = ?
                """,
                (workspace_id, channel_id, selected_ts),
            ).fetchone()
            if reply_count is not None and int(reply_count["count"] or 0) > 0:
                thread_root = selected_ts

        stream_kind = "slack-thread" if thread_root else "slack-channel"
        stream_id = (
            f"slack-thread|{workspace}|{channel_id}|{thread_root}"
            if thread_root
            else f"slack-channel|{workspace}|{channel_id}"
        )

        cursor_ts = selected_ts
        if normalized_direction in {"before", "after"}:
            decoded = _decode_context_cursor(str(cursor or ""))
            if (
                decoded.get("stream_id") != stream_id
                or decoded.get("workspace") != workspace
                or decoded.get("channel_id") != channel_id
            ):
                raise ValueError("context cursor does not match result stream")
            cursor_ts = str(decoded.get("ts") or "").strip()
            if not cursor_ts:
                raise ValueError("context cursor is missing ts")

        if normalized_direction == "around":
            before_limit = max(0, (item_limit - 1) // 2)
            after_limit = max(0, item_limit - 1 - before_limit)
            rows = [
                *reversed(
                    self._context_window_rows(
                        conn,
                        workspace_id=workspace_id,
                        channel_id=channel_id,
                        stream_kind=stream_kind,
                        thread_root=thread_root,
                        anchor_ts=selected_ts,
                        direction="before",
                        limit=before_limit,
                    )
                ),
                hit,
                *self._context_window_rows(
                    conn,
                    workspace_id=workspace_id,
                    channel_id=channel_id,
                    stream_kind=stream_kind,
                    thread_root=thread_root,
                    anchor_ts=selected_ts,
                    direction="after",
                    limit=after_limit,
                ),
            ]
        else:
            rows = self._context_window_rows(
                conn,
                workspace_id=workspace_id,
                channel_id=channel_id,
                stream_kind=stream_kind,
                thread_root=thread_root,
                anchor_ts=cursor_ts,
                direction=normalized_direction,
                limit=item_limit,
            )
            if normalized_direction == "before":
                rows = list(reversed(rows))

        mention_ids = {mention_id for row in rows for mention_id in slack_user_mention_ids(dict(row).get("text"))}
        mention_labels = workspace_user_mention_labels(conn, workspace_id=workspace_id, user_ids=mention_ids)
        items = [
            self._project_context_window_message(
                row,
                workspace=workspace,
                workspace_id=workspace_id,
                selected_ts=selected_ts,
                stream_kind=stream_kind,
                thread_root=thread_root,
                include_text=include_text,
                max_text_chars=text_limit,
                mention_labels=mention_labels,
            )
            for row in rows
        ]
        first_ts = str(items[0]["nativeIds"]["ts"]) if items else cursor_ts
        last_ts = str(items[-1]["nativeIds"]["ts"]) if items else cursor_ts
        has_before = self._context_window_has_neighbor(
            conn,
            workspace_id=workspace_id,
            channel_id=channel_id,
            stream_kind=stream_kind,
            thread_root=thread_root,
            anchor_ts=first_ts,
            direction="before",
        )
        has_after = self._context_window_has_neighbor(
            conn,
            workspace_id=workspace_id,
            channel_id=channel_id,
            stream_kind=stream_kind,
            thread_root=thread_root,
            anchor_ts=last_ts,
            direction="after",
        )
        before_cursor = (
            _encode_context_cursor(
                {
                    "stream_id": stream_id,
                    "workspace": workspace,
                    "channel_id": channel_id,
                    "thread_root": thread_root,
                    "ts": first_ts,
                }
            )
            if items
            else None
        )
        after_cursor = (
            _encode_context_cursor(
                {
                    "stream_id": stream_id,
                    "workspace": workspace,
                    "channel_id": channel_id,
                    "thread_root": thread_root,
                    "ts": last_ts,
                }
            )
            if items
            else None
        )
        channel_name = hit.get("channel_name")
        stream_label = f"#{channel_name}" if channel_name else channel_id
        if stream_kind == "slack-thread":
            stream_label = f"{stream_label} / thread"
        return {
            "schemaVersion": 1,
            "service": "slack",
            "resultId": result_id,
            "streamId": stream_id,
            "streamLabel": stream_label,
            "streamKind": stream_kind,
            "tenantLabel": workspace,
            "scopeLabel": workspace,
            "selectedItemId": f"message|{workspace}|{channel_id}|{selected_ts}",
            "items": items,
            "pageInfo": {
                "hasBefore": has_before,
                "hasAfter": has_after,
                "beforeCursor": before_cursor,
                "afterCursor": after_cursor,
            },
        }

    def list_child_events(
        self,
        conn,
        *,
        tenant: str | None = None,
        after: str | None = None,
        limit: int = 50,
        service_kind: str | None = None,
        account_key: str | None = None,
        event_type: str | None = None,
        privacy: str | None = None,
        actor_ref: str | None = None,
        actor_user_id: str | None = None,
        channel_ref: str | None = None,
        channel_id: str | None = None,
        subject_kind: str | None = None,
        subject_id: str | None = None,
        journal_only: bool = False,
    ) -> dict[str, Any]:
        if service_kind and str(service_kind).strip().lower() not in {"slack", "slack-mirror"}:
            return self._event_page([], limit=max(1, min(int(limit), 100)), status="complete")
        item_limit = max(1, min(int(limit), 100))
        after_tuple = _decode_event_cursor(after)
        events = self._matching_child_events(
            conn,
            tenant=tenant,
            account_key=account_key,
            event_type=event_type,
            privacy=privacy,
            actor_ref=actor_ref,
            actor_user_id=actor_user_id,
            channel_ref=channel_ref,
            channel_id=channel_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
            include_derived=not journal_only,
        )
        stale_cursor = False
        if after_tuple is not None:
            if events:
                oldest_tuple = (str(events[0].get("recordedAt") or ""), str(events[0].get("id") or ""))
                stale_cursor = after_tuple < oldest_tuple
            events = [
                event
                for event in events
                if (str(event.get("recordedAt") or ""), str(event.get("id") or "")) > after_tuple
            ]
        status = "stale-cursor" if stale_cursor else "complete"
        return self._event_page(events, limit=item_limit, status=status, stale_cursor=stale_cursor)

    def follow_child_events(
        self,
        conn,
        *,
        tenant: str | None = None,
        after: str | None = None,
        limit: int = 50,
        timeout_ms: int = 0,
        service_kind: str | None = None,
        account_key: str | None = None,
        event_type: str | None = None,
        privacy: str | None = None,
        actor_ref: str | None = None,
        actor_user_id: str | None = None,
        channel_ref: str | None = None,
        channel_id: str | None = None,
        subject_kind: str | None = None,
        subject_id: str | None = None,
    ) -> dict[str, Any]:
        wait_seconds = max(0.0, min(float(timeout_ms) / 1000.0, 30.0))
        deadline = time.monotonic() + wait_seconds
        while True:
            payload = self.list_child_events(
                conn,
                tenant=tenant,
                after=after,
                limit=limit,
                service_kind=service_kind,
                account_key=account_key,
                event_type=event_type,
                privacy=privacy,
                actor_ref=actor_ref,
                actor_user_id=actor_user_id,
                channel_ref=channel_ref,
                channel_id=channel_id,
                subject_kind=subject_kind,
                subject_id=subject_id,
                journal_only=True,
            )
            if payload["count"] or payload["stale_cursor"] or time.monotonic() >= deadline:
                payload["follow"] = {
                    "mode": "bounded-long-poll",
                    "journalOnly": True,
                    "journal_only": True,
                    "timeoutMs": int(wait_seconds * 1000),
                    "timeout_ms": int(wait_seconds * 1000),
                }
                payload["statusText"] = (
                    "Journal follow returned matching event(s)."
                    if payload["count"]
                    else "Journal follow timed out without matching events."
                )
                payload["status_text"] = payload["statusText"]
                return payload
            time.sleep(0.25)

    def child_event_status(
        self,
        conn,
        *,
        tenant: str | None = None,
        service_kind: str | None = None,
        account_key: str | None = None,
        event_type: str | None = None,
        privacy: str | None = None,
        actor_ref: str | None = None,
        actor_user_id: str | None = None,
        channel_ref: str | None = None,
        channel_id: str | None = None,
        subject_kind: str | None = None,
        subject_id: str | None = None,
    ) -> dict[str, Any]:
        if service_kind and str(service_kind).strip().lower() not in {"slack", "slack-mirror"}:
            events: list[dict[str, Any]] = []
        else:
            events = self._matching_child_events(
                conn,
                tenant=tenant,
                account_key=account_key,
                event_type=event_type,
                privacy=privacy,
                actor_ref=actor_ref,
                actor_user_id=actor_user_id,
                channel_ref=channel_ref,
                channel_id=channel_id,
                subject_kind=subject_kind,
                subject_id=subject_id,
                include_derived=True,
            )
        unfiltered_events: list[dict[str, Any]] = []
        if not service_kind or str(service_kind).strip().lower() in {"slack", "slack-mirror"}:
            unfiltered_events = self._matching_child_events(
                conn,
                tenant=tenant,
                account_key=account_key,
                event_type=None,
                privacy=None,
                actor_ref=None,
                actor_user_id=None,
                channel_ref=None,
                channel_id=None,
                subject_kind=None,
                subject_id=None,
                include_derived=True,
            )
        latest = events[-1] if events else None
        oldest = events[0] if events else None
        watermark_by_type: dict[str, dict[str, Any]] = {}
        family_counts: dict[str, int] = {}
        for event in events:
            event_type_key = str(event.get("eventType") or "")
            family_counts[event_type_key] = family_counts.get(event_type_key, 0) + 1
            current = watermark_by_type.get(event_type_key)
            current_count = int(current.get("count") or 0) if current else 0
            if current is None or (
                str(event.get("recordedAt") or ""),
                str(event.get("id") or ""),
            ) > (
                str(current.get("latest_recorded_at") or ""),
                str(current.get("latest_event_id") or ""),
            ):
                event_cursor = _event_cursor_for(event)
                watermark_by_type[event_type_key] = {
                    "event_type": event.get("eventType"),
                    "eventType": event.get("eventType"),
                    "count": current_count,
                    "latest_event_id": event.get("id"),
                    "latestEventId": event.get("id"),
                    "latest_recorded_at": event.get("recordedAt"),
                    "latestRecordedAt": event.get("recordedAt"),
                    "latest_occurred_at": event.get("occurredAt"),
                    "latestOccurredAt": event.get("occurredAt"),
                    "latest_cursor": event_cursor,
                    "latestCursor": event_cursor,
                }
            watermark_by_type[event_type_key]["count"] += 1
        latest_cursor = None
        if latest:
            latest_cursor = _event_cursor_for(latest)
        oldest_cursor = _event_cursor_for(oldest) if oldest else None
        if events:
            status = "current"
            status_text = "Event cursor is current."
            recovery = {"action": "continue", "message": "Continue reading from latest_cursor or the next page cursor."}
        elif unfiltered_events:
            status = "filtered-empty"
            status_text = "Slack events exist, but none match the supplied filters."
            recovery = {"action": "relax_filters", "message": "Relax event_type, privacy, tenant, or account filters."}
        else:
            status = "empty"
            status_text = "No Slack events are available for the selected scope."
            recovery = {"action": "wait_or_sync", "message": "Wait for live sync or run a bounded backfill/reconcile for this tenant."}
        return {
            "schemaVersion": 1,
            "schema_version": 1,
            "service": "slack",
            "status": status,
            "statusText": status_text,
            "status_text": status_text,
            "eventCount": len(events),
            "event_count": len(events),
            "eventFamilyCounts": family_counts,
            "event_family_counts": family_counts,
            "latestEventId": latest.get("id") if latest else None,
            "latest_event_id": latest.get("id") if latest else None,
            "latestRecordedAt": latest.get("recordedAt") if latest else None,
            "latest_recorded_at": latest.get("recordedAt") if latest else None,
            "latestOccurredAt": latest.get("occurredAt") if latest else None,
            "latest_occurred_at": latest.get("occurredAt") if latest else None,
            "latestCursor": latest_cursor,
            "latest_cursor": latest_cursor,
            "oldestEventId": oldest.get("id") if oldest else None,
            "oldest_event_id": oldest.get("id") if oldest else None,
            "oldestRecordedAt": oldest.get("recordedAt") if oldest else None,
            "oldest_recorded_at": oldest.get("recordedAt") if oldest else None,
            "oldestCursor": oldest_cursor,
            "oldest_cursor": oldest_cursor,
            "cursorRetention": {
                "mode": "derived-from-current-state",
                "oldestCursor": oldest_cursor,
                "oldest_cursor": oldest_cursor,
                "staleCursorStatus": "stale-cursor",
                "stale_cursor_status": "stale-cursor",
            },
            "cursor_retention": {
                "mode": "derived-from-current-state",
                "oldestCursor": oldest_cursor,
                "oldest_cursor": oldest_cursor,
                "staleCursorStatus": "stale-cursor",
                "stale_cursor_status": "stale-cursor",
            },
            "partial": False,
            "failed": False,
            "degraded": False,
            "recovery": recovery,
            "recoveryGuidance": recovery,
            "recovery_guidance": recovery,
            "watermarks": list(watermark_by_type.values()),
            "descriptors": child_event_descriptors(),
        }

    def _matching_child_events(
        self,
        conn,
        *,
        tenant: str | None,
        account_key: str | None,
        event_type: str | None,
        privacy: str | None,
        actor_ref: str | None,
        actor_user_id: str | None,
        channel_ref: str | None,
        channel_id: str | None,
        subject_kind: str | None,
        subject_id: str | None,
        include_derived: bool = True,
    ) -> list[dict[str, Any]]:
        privacy_filter = {part.strip() for part in str(privacy or "").split(",") if part.strip()}
        event_type_filter = {part.strip() for part in str(event_type or "").split(",") if part.strip()}
        workspace_filter = str(tenant or account_key or "").strip()
        events = [*self._journal_child_events(conn, workspace_filter=workspace_filter or None)]
        if include_derived:
            events.extend(
                [
                    *self._message_child_events(conn, workspace_filter=workspace_filter or None),
                    *self._file_child_events(conn, workspace_filter=workspace_filter or None),
                    *self._export_child_events(workspace_filter=workspace_filter or None),
                    *self._export_lifecycle_events(workspace_filter=workspace_filter or None),
                ]
            )
        if event_type_filter:
            events = [event for event in events if str(event.get("eventType") or "") in event_type_filter]
        if privacy_filter:
            events = [event for event in events if str(event.get("privacy") or "") in privacy_filter]
        if any([actor_ref, actor_user_id, channel_ref, channel_id, subject_kind, subject_id]):
            events = [
                event
                for event in events
                if _event_matches_receipts_filters(
                    event,
                    actor_ref=actor_ref,
                    actor_user_id=actor_user_id,
                    channel_ref=channel_ref,
                    channel_id=channel_id,
                    subject_kind=subject_kind,
                    subject_id=subject_id,
                )
            ]
        events.sort(key=lambda event: (str(event.get("recordedAt") or ""), str(event.get("id") or "")))
        return events

    def _journal_child_events(self, conn, *, workspace_filter: str | None) -> list[dict[str, Any]]:
        params: list[Any] = []
        workspace_clause = ""
        if workspace_filter:
            workspace_clause = "WHERE w.name = ?"
            params.append(workspace_filter)
        try:
            rows = conn.execute(
                f"""
                SELECT w.name AS workspace,
                       ce.workspace_id,
                       ce.event_id,
                       ce.event_type,
                       ce.subject_kind,
                       ce.subject_id,
                       ce.actor_user_id,
                       COALESCE(ce.actor_label, u.display_name, u.real_name, u.username, ce.actor_user_id) AS actor_label,
                       ce.channel_id,
                       c.name AS channel_name,
                       ce.privacy,
                       ce.occurred_at,
                       ce.recorded_at,
                       ce.source_refs_json,
                       ce.payload_json
                FROM child_event_journal ce
                JOIN workspaces w ON w.id = ce.workspace_id
                LEFT JOIN users u ON u.workspace_id = ce.workspace_id AND u.user_id = ce.actor_user_id
                LEFT JOIN channels c ON c.workspace_id = ce.workspace_id AND c.channel_id = ce.channel_id
                {workspace_clause}
                """,
                tuple(params),
            ).fetchall()
        except Exception:  # noqa: BLE001 - older fixture DBs may not have the journal table yet.
            return []
        events: list[dict[str, Any]] = []
        for row_obj in rows:
            row = dict(row_obj)
            source_refs = _json_dict(row.get("source_refs_json"))
            source_refs.setdefault("workspace", row.get("workspace"))
            if row.get("channel_id"):
                source_refs.setdefault("channel_id", row.get("channel_id"))
            if row.get("channel_name"):
                source_refs.setdefault("channel_name", row.get("channel_name"))
            if row.get("actor_user_id"):
                source_refs.setdefault("user_id", row.get("actor_user_id"))
            if row.get("actor_label"):
                source_refs.setdefault("user_label", row.get("actor_label"))
            payload = _json_dict(row.get("payload_json"))
            if row.get("channel_id"):
                payload.setdefault("channelLabel", f"#{row.get('channel_name')}" if row.get("channel_name") else row.get("channel_id"))
            if row.get("actor_label"):
                payload.setdefault("senderLabel", row.get("actor_label"))
            event_type = str(row.get("event_type") or "")
            subject = {"kind": row.get("subject_kind"), "id": row.get("subject_id")}
            actor = None
            if row.get("actor_user_id") or row.get("actor_label"):
                actor = {"kind": "slack-user", "id": row.get("actor_user_id"), "label": row.get("actor_label")}
            events.append(
                self._event_with_aliases(
                    {
                        "id": str(row.get("event_id") or ""),
                        "eventType": event_type,
                        "subject": subject,
                        "actor": actor,
                        "actorUserId": row.get("actor_user_id"),
                        "actorLabel": row.get("actor_label"),
                        "occurredAt": _sqlite_timestamp_to_iso(row.get("occurred_at")),
                        "recordedAt": _sqlite_timestamp_to_iso(row.get("recorded_at")),
                        "title": _journal_event_title(event_type),
                        "summary": _journal_event_summary(event_type, row, payload),
                        "serviceKind": "slack",
                        "accountKey": row.get("workspace"),
                        "tenant": row.get("workspace"),
                        "privacy": row.get("privacy") or "user",
                        "sourceRefs": source_refs,
                        "payload": payload,
                    }
                )
            )
        return events

    def _export_event_log_path(self) -> Path:
        return resolve_export_root(self.config) / ".slack-mirror-events.jsonl"

    def _append_export_lifecycle_event(
        self,
        *,
        event_type: str,
        export_id: str,
        workspace: str,
        manifest: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        log_path = self._export_event_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "schemaVersion": 1,
            "id": f"{event_type}|{export_id}|{now}",
            "eventType": event_type,
            "subject": {"kind": "slack-export", "id": export_id},
            "occurredAt": now,
            "recordedAt": now,
            "title": {
                "slack.export.renamed": "Slack export renamed",
                "slack.export.deleted": "Slack export deleted",
            }.get(event_type, "Slack export lifecycle event"),
            "summary": {
                "slack.export.renamed": f"Export {payload.get('oldExportId')} renamed to {payload.get('newExportId')}",
                "slack.export.deleted": f"Export {export_id} deleted",
            }.get(event_type, f"Export {export_id} lifecycle event"),
            "serviceKind": "slack",
            "accountKey": workspace or None,
            "tenant": workspace or None,
            "privacy": "user",
            "sourceRefs": {
                "export_id": export_id,
                "old_export_id": payload.get("oldExportId"),
                "new_export_id": payload.get("newExportId"),
                "kind": manifest.get("kind"),
                "bundle_url": manifest.get("bundle_url"),
            },
            "payload": {
                **payload,
                "kind": manifest.get("kind"),
                "title": manifest.get("title"),
                "itemCount": manifest.get("item_count"),
                "resolvedCount": manifest.get("resolved_count"),
                "fileCount": manifest.get("file_count"),
            },
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _export_lifecycle_events(self, *, workspace_filter: str | None) -> list[dict[str, Any]]:
        log_path = self._export_event_log_path()
        if not log_path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            workspace = str(event.get("tenant") or event.get("accountKey") or "").strip()
            if workspace_filter and workspace != workspace_filter:
                continue
            events.append(self._event_with_aliases(event))
        return events

    def _event_with_aliases(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        source_refs = dict(payload.get("sourceRefs") or {})
        actor = dict(payload.get("actor") or {})
        payload.setdefault("event_type", payload.get("eventType"))
        payload.setdefault("occurred_at", payload.get("occurredAt"))
        payload.setdefault("recorded_at", payload.get("recordedAt"))
        payload.setdefault("service_kind", payload.get("serviceKind"))
        payload.setdefault("account_key", payload.get("accountKey"))
        payload.setdefault("source_refs", source_refs)
        payload.setdefault("native_ids", source_refs)
        payload.setdefault("nativeIds", source_refs)
        payload.setdefault("actor_user_id", payload.get("actorUserId") or actor.get("id") or source_refs.get("user_id"))
        payload.setdefault("actor_label", payload.get("actorLabel") or actor.get("label") or source_refs.get("user_label"))
        return payload

    def _event_page(self, events: list[dict[str, Any]], *, limit: int, status: str, stale_cursor: bool = False) -> dict[str, Any]:
        page = events[:limit]
        next_cursor = None
        oldest_cursor = _event_cursor_for(events[0]) if events else None
        latest_cursor = _event_cursor_for(events[-1]) if events else None
        if page:
            last = page[-1]
            next_cursor = _event_cursor_for(last)
            for event in page:
                event["cursor"] = _event_cursor_for(event)
        status_text = "Event page read completed."
        if stale_cursor:
            status_text = "The supplied cursor is older than the current event window; reset from oldest_cursor or latest_cursor."
        return {
            "schemaVersion": 1,
            "schema_version": 1,
            "service": "slack",
            "status": status,
            "statusText": status_text,
            "status_text": status_text,
            "events": page,
            "nextCursor": next_cursor,
            "next_cursor": next_cursor,
            "oldestCursor": oldest_cursor,
            "oldest_cursor": oldest_cursor,
            "latestCursor": latest_cursor,
            "latest_cursor": latest_cursor,
            "hasMore": len(events) > limit,
            "has_more": len(events) > limit,
            "staleCursor": stale_cursor,
            "stale_cursor": stale_cursor,
            "recovery": {
                "action": "reset_cursor" if stale_cursor else "continue",
                "message": status_text if stale_cursor else "Continue with next_cursor when hasMore is true.",
            },
            "count": len(page),
        }

    def _message_child_events(self, conn, *, workspace_filter: str | None) -> list[dict[str, Any]]:
        params: list[Any] = []
        workspace_clause = ""
        if workspace_filter:
            workspace_clause = "WHERE w.name = ?"
            params.append(workspace_filter)
        rows = conn.execute(
            f"""
            SELECT w.name AS workspace, w.id AS workspace_id, m.channel_id, c.name AS channel_name,
                   m.ts, m.thread_ts, m.user_id,
                   COALESCE(u.display_name, u.real_name, u.username, m.user_id) AS user_label,
                   m.subtype, m.text, m.updated_at
            FROM messages m
            JOIN workspaces w ON w.id = m.workspace_id
            LEFT JOIN channels c ON c.workspace_id = m.workspace_id AND c.channel_id = m.channel_id
            LEFT JOIN users u ON u.workspace_id = m.workspace_id AND u.user_id = m.user_id
            {workspace_clause}
            """,
            tuple(params),
        ).fetchall()
        events: list[dict[str, Any]] = []
        for row_obj in rows:
            row = dict(row_obj)
            workspace = str(row.get("workspace") or "")
            channel_id = str(row.get("channel_id") or "")
            ts = str(row.get("ts") or "")
            is_reply = bool(row.get("thread_ts")) and str(row.get("thread_ts")) != ts
            event_type = "slack.thread_reply.observed" if is_reply else "slack.message.observed"
            channel_label = f"#{row.get('channel_name')}" if row.get("channel_name") else channel_id
            sender_label = row.get("user_label") or "Unknown"
            text = _truncate_text(row.get("text"), 160)
            events.append(
                self._event_with_aliases(
                    {
                        "id": f"{event_type}|{workspace}|{channel_id}|{ts}",
                        "eventType": event_type,
                        "subject": {"kind": "slack-message", "id": f"message|{workspace}|{channel_id}|{ts}"},
                        "occurredAt": _slack_ts_to_iso(ts) or _sqlite_timestamp_to_iso(row.get("updated_at")),
                        "recordedAt": _sqlite_timestamp_to_iso(row.get("updated_at")) or _slack_ts_to_iso(ts),
                        "title": "Thread reply observed" if is_reply else "Slack message observed",
                        "summary": (
                            f"{sender_label} in {channel_label}: {text}"
                            if text
                            else f"{sender_label} in {channel_label}"
                        ),
                        "actor": {
                            "kind": "slack-user",
                            "id": row.get("user_id"),
                            "label": sender_label,
                        },
                        "actorUserId": row.get("user_id"),
                        "actorLabel": sender_label,
                        "serviceKind": "slack",
                        "accountKey": workspace,
                        "tenant": workspace,
                        "privacy": "user",
                        "sourceRefs": {
                            "workspace": workspace,
                            "workspace_id": row.get("workspace_id"),
                            "channel_id": channel_id,
                            "channel_name": row.get("channel_name"),
                            "ts": ts,
                            "thread_ts": row.get("thread_ts"),
                            "user_id": row.get("user_id"),
                            "user_label": sender_label,
                        },
                        "payload": {
                            "channelLabel": channel_label,
                            "senderLabel": sender_label,
                            "textPreview": text,
                            "subtype": row.get("subtype"),
                        },
                    }
                )
            )
        return events

    def _file_child_events(self, conn, *, workspace_filter: str | None) -> list[dict[str, Any]]:
        params: list[Any] = []
        workspace_clause = ""
        if workspace_filter:
            workspace_clause = "WHERE w.name = ?"
            params.append(workspace_filter)
        rows = conn.execute(
            f"""
            SELECT w.name AS workspace, w.id AS workspace_id, mf.channel_id, c.name AS channel_name,
                   mf.ts, mf.file_id, mf.created_at, f.name, f.title, f.mimetype
            FROM message_files mf
            JOIN workspaces w ON w.id = mf.workspace_id
            LEFT JOIN channels c ON c.workspace_id = mf.workspace_id AND c.channel_id = mf.channel_id
            LEFT JOIN files f ON f.workspace_id = mf.workspace_id AND f.file_id = mf.file_id
            {workspace_clause}
            """,
            tuple(params),
        ).fetchall()
        events: list[dict[str, Any]] = []
        for row_obj in rows:
            row = dict(row_obj)
            workspace = str(row.get("workspace") or "")
            channel_id = str(row.get("channel_id") or "")
            file_id = str(row.get("file_id") or "")
            ts = str(row.get("ts") or "")
            label = row.get("title") or row.get("name") or file_id
            channel_label = f"#{row.get('channel_name')}" if row.get("channel_name") else channel_id
            events.append(
                self._event_with_aliases(
                    {
                        "id": f"slack.file.linked|{workspace}|{channel_id}|{ts}|{file_id}",
                        "eventType": "slack.file.linked",
                        "subject": {"kind": "slack-file", "id": file_id},
                        "occurredAt": _slack_ts_to_iso(ts) or _sqlite_timestamp_to_iso(row.get("created_at")),
                        "recordedAt": _sqlite_timestamp_to_iso(row.get("created_at")) or _slack_ts_to_iso(ts),
                        "title": "Slack file linked",
                        "summary": f"{label} linked in {channel_label}",
                        "serviceKind": "slack",
                        "accountKey": workspace,
                        "tenant": workspace,
                        "privacy": "user",
                        "sourceRefs": {
                            "workspace": workspace,
                            "workspace_id": row.get("workspace_id"),
                            "channel_id": channel_id,
                            "channel_name": row.get("channel_name"),
                            "ts": ts,
                            "file_id": file_id,
                        },
                        "payload": {
                            "fileLabel": label,
                            "mimetype": row.get("mimetype"),
                            "channelLabel": channel_label,
                        },
                    }
                )
            )
        return events

    def _export_child_events(self, *, workspace_filter: str | None) -> list[dict[str, Any]]:
        export_root = resolve_export_root(self.config)
        if not export_root.exists():
            return []
        events: list[dict[str, Any]] = []
        for manifest in list_export_manifests(
            export_root,
            base_urls=resolve_export_base_urls(self.config),
            default_audience="local",
        ):
            workspace = str(manifest.get("workspace") or "").strip()
            if workspace_filter and workspace != workspace_filter:
                continue
            export_id = str(manifest.get("export_id") or "")
            if not export_id:
                continue
            bundle_dir = export_root / export_id
            recorded_at = datetime.fromtimestamp(bundle_dir.stat().st_mtime, tz=UTC).isoformat().replace("+00:00", "Z")
            kind = str(manifest.get("kind") or "export-bundle")
            title = str(manifest.get("title") or export_id)
            events.append(
                self._event_with_aliases(
                    {
                        "id": f"slack.export.created|{export_id}",
                        "eventType": "slack.export.created",
                        "subject": {"kind": "slack-export", "id": export_id},
                        "occurredAt": recorded_at,
                        "recordedAt": recorded_at,
                        "title": "Slack export created",
                        "summary": f"{kind} export {title}",
                        "serviceKind": "slack",
                        "accountKey": workspace or None,
                        "tenant": workspace or None,
                        "privacy": "user",
                        "sourceRefs": {"export_id": export_id, "kind": kind, "bundle_url": manifest.get("bundle_url")},
                        "payload": {
                            "title": title,
                            "kind": kind,
                            "itemCount": manifest.get("item_count"),
                            "resolvedCount": manifest.get("resolved_count"),
                            "fileCount": manifest.get("file_count"),
                        },
                    }
                )
            )
        return events

    def _message_context_pack_item(
        self,
        conn,
        *,
        target: dict[str, Any],
        before: int,
        after: int,
        include_text: bool,
        max_text_chars: int,
    ) -> dict[str, Any]:
        workspace = str(target.get("workspace") or "").strip()
        channel_id = str(target.get("channel_id") or "").strip()
        ts = str(target.get("ts") or "").strip()
        if not workspace or not channel_id or not ts:
            return {"kind": "message", "target": target, "resolved": False, "reason": "missing_message_identity"}
        workspace_id = self.workspace_id(conn, workspace)
        hit = self._message_context_row(conn, workspace=workspace, workspace_id=workspace_id, channel_id=channel_id, ts=ts)
        if hit is None:
            return {"kind": "message", "target": target, "resolved": False, "reason": "message_not_found"}
        before_rows = conn.execute(
            """
            SELECT m.channel_id, c.name AS channel_name, m.ts, m.thread_ts, m.user_id,
                   u.username AS user_name,
                   u.display_name AS user_display_name,
                   COALESCE(u.display_name, u.real_name, u.username, m.user_id) AS user_label,
                   m.subtype, m.text, m.edited_ts, m.deleted, m.raw_json
            FROM messages m
            LEFT JOIN channels c ON c.workspace_id = m.workspace_id AND c.channel_id = m.channel_id
            LEFT JOIN users u ON u.workspace_id = m.workspace_id AND u.user_id = m.user_id
            WHERE m.workspace_id = ? AND m.channel_id = ? AND CAST(m.ts AS REAL) < CAST(? AS REAL)
            ORDER BY CAST(m.ts AS REAL) DESC
            LIMIT ?
            """,
            (workspace_id, channel_id, ts, before),
        ).fetchall()
        after_rows = conn.execute(
            """
            SELECT m.channel_id, c.name AS channel_name, m.ts, m.thread_ts, m.user_id,
                   u.username AS user_name,
                   u.display_name AS user_display_name,
                   COALESCE(u.display_name, u.real_name, u.username, m.user_id) AS user_label,
                   m.subtype, m.text, m.edited_ts, m.deleted, m.raw_json
            FROM messages m
            LEFT JOIN channels c ON c.workspace_id = m.workspace_id AND c.channel_id = m.channel_id
            LEFT JOIN users u ON u.workspace_id = m.workspace_id AND u.user_id = m.user_id
            WHERE m.workspace_id = ? AND m.channel_id = ? AND CAST(m.ts AS REAL) > CAST(? AS REAL)
            ORDER BY CAST(m.ts AS REAL) ASC
            LIMIT ?
            """,
            (workspace_id, channel_id, ts, after),
        ).fetchall()
        message_rows = [*reversed(before_rows), hit, *after_rows]
        mention_ids: set[str] = set()
        for row in message_rows:
            mention_ids.update(slack_user_mention_ids(dict(row).get("text")))
        mention_labels = workspace_user_mention_labels(conn, workspace_id=workspace_id, user_ids=mention_ids)
        context = [
            *[
                _project_context_message(
                    row,
                    workspace=workspace,
                    relation="before",
                    selected=False,
                    include_text=include_text,
                    max_text_chars=max_text_chars,
                    mention_labels=mention_labels,
                )
                for row in message_rows[: len(before_rows)]
            ],
            _project_context_message(
                hit,
                workspace=workspace,
                relation="hit",
                selected=True,
                include_text=include_text,
                max_text_chars=max_text_chars,
                mention_labels=mention_labels,
            ),
            *[
                _project_context_message(
                    row,
                    workspace=workspace,
                    relation="after",
                    selected=False,
                    include_text=include_text,
                    max_text_chars=max_text_chars,
                    mention_labels=mention_labels,
                )
                for row in after_rows
            ],
        ]
        return {
            "kind": "message",
            "target": target,
            "resolved": True,
            "workspace": workspace,
            "workspace_id": workspace_id,
            "conversation": {
                "kind": "slack_channel",
                "channel_id": channel_id,
                "channel_name": hit.get("channel_name"),
            },
            "hit": _project_context_message(
                hit,
                workspace=workspace,
                relation="hit",
                selected=True,
                include_text=include_text,
                max_text_chars=max_text_chars,
                mention_labels=mention_labels,
            ),
            "context": context,
        }

    def _context_window_where_clause(self, *, stream_kind: str) -> str:
        if stream_kind == "slack-thread":
            return "AND (m.ts = ? OR m.thread_ts = ?)"
        return ""

    def _context_window_rows(
        self,
        conn,
        *,
        workspace_id: int,
        channel_id: str,
        stream_kind: str,
        thread_root: str,
        anchor_ts: str,
        direction: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        comparator = "<" if direction == "before" else ">"
        ordering = "DESC" if direction == "before" else "ASC"
        stream_clause = self._context_window_where_clause(stream_kind=stream_kind)
        params: list[Any] = [workspace_id, channel_id]
        if stream_kind == "slack-thread":
            params.extend([thread_root, thread_root])
        params.extend([anchor_ts, limit])
        rows = conn.execute(
            f"""
            SELECT m.channel_id, c.name AS channel_name, m.ts, m.thread_ts, m.user_id,
                   u.username AS user_name,
                   u.display_name AS user_display_name,
                   COALESCE(u.display_name, u.real_name, u.username, m.user_id) AS user_label,
                   m.subtype, m.text, m.edited_ts, m.deleted, m.raw_json
            FROM messages m
            LEFT JOIN channels c ON c.workspace_id = m.workspace_id AND c.channel_id = m.channel_id
            LEFT JOIN users u ON u.workspace_id = m.workspace_id AND u.user_id = m.user_id
            WHERE m.workspace_id = ? AND m.channel_id = ?
              {stream_clause}
              AND CAST(m.ts AS REAL) {comparator} CAST(? AS REAL)
            ORDER BY CAST(m.ts AS REAL) {ordering}
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [dict(row) for row in rows]

    def _context_window_has_neighbor(
        self,
        conn,
        *,
        workspace_id: int,
        channel_id: str,
        stream_kind: str,
        thread_root: str,
        anchor_ts: str,
        direction: str,
    ) -> bool:
        return bool(
            self._context_window_rows(
                conn,
                workspace_id=workspace_id,
                channel_id=channel_id,
                stream_kind=stream_kind,
                thread_root=thread_root,
                anchor_ts=anchor_ts,
                direction=direction,
                limit=1,
            )
        )

    def _project_context_window_message(
        self,
        row: dict[str, Any],
        *,
        workspace: str,
        workspace_id: int,
        selected_ts: str,
        stream_kind: str,
        thread_root: str,
        include_text: bool,
        max_text_chars: int,
        mention_labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload = dict(row)
        ts = str(payload.get("ts") or "")
        channel_id = str(payload.get("channel_id") or "")
        raw = {}
        try:
            raw = json.loads(str(payload.get("raw_json") or "{}"))
        except json.JSONDecodeError:
            raw = {}
        files = raw.get("files") if isinstance(raw, dict) else None
        artifacts = []
        if isinstance(files, list):
            for file_obj in files:
                if not isinstance(file_obj, dict):
                    continue
                artifacts.append(
                    {
                        "kind": "slack-file",
                        "id": file_obj.get("id"),
                        "name": file_obj.get("name") or file_obj.get("title"),
                        "title": file_obj.get("title"),
                        "mimetype": file_obj.get("mimetype"),
                        "permalink": file_obj.get("permalink"),
                    }
                )
        item = {
            "id": f"message|{workspace}|{channel_id}|{ts}",
            "itemId": f"message|{workspace}|{channel_id}|{ts}",
            "kind": "slack-message",
            "timestamp": ts,
            "timestampIso": _slack_ts_to_iso(ts),
            "senderLabel": payload.get("user_label") or payload.get("user_id") or "Unknown",
            "selected": ts == selected_ts,
            "nativeIds": {
                "workspace": workspace,
                "workspaceId": workspace_id,
                "channelId": channel_id,
                "channelName": payload.get("channel_name"),
                "ts": ts,
                "threadTs": thread_root or payload.get("thread_ts"),
                "userId": payload.get("user_id"),
            },
            "sourceRefs": {
                "service": "slack",
                "workspace": workspace,
                "channel_id": channel_id,
                "channel_name": payload.get("channel_name"),
                "ts": ts,
                "thread_ts": thread_root or payload.get("thread_ts"),
            },
            "sender": {
                "id": payload.get("user_id"),
                "label": payload.get("user_label"),
                "username": payload.get("user_name"),
                "displayName": payload.get("user_display_name"),
            },
            "slack": {
                "workspace": workspace,
                "workspaceId": workspace_id,
                "channelId": channel_id,
                "channelName": payload.get("channel_name"),
                "ts": ts,
                "threadTs": thread_root or payload.get("thread_ts"),
                "streamKind": stream_kind,
                "subtype": payload.get("subtype"),
                "editedTs": payload.get("edited_ts"),
                "deleted": bool(payload.get("deleted")),
            },
            "artifacts": artifacts,
            "actionTarget": {
                "version": 1,
                "kind": "message",
                "id": f"message|{workspace}|{channel_id}|{ts}",
                "workspace": workspace,
                "workspace_id": workspace_id,
                "channel_id": channel_id,
                "channel_name": payload.get("channel_name"),
                "ts": ts,
                "thread_ts": thread_root or payload.get("thread_ts"),
                "user_id": payload.get("user_id"),
                "selection_label": f"{workspace}:{channel_id}:{ts}",
            },
        }
        if include_text:
            raw_text = _truncate_text(payload.get("text"), max_text_chars)
            guest_safe_text = render_guest_safe_user_mentions(raw_text, mention_labels or {})
            item["text"] = guest_safe_text
            if guest_safe_text != raw_text:
                item["rawText"] = raw_text
                item["textRendering"] = {
                    "kind": "slack_mrkdwn_guest_safe",
                    "mentions": "user_display_labels",
                    "emoji": "common_unicode_aliases",
                    "unresolvedUserPlaceholder": "@unresolved-slack-user",
                }
        return item

    def _message_context_row(
        self,
        conn,
        *,
        workspace: str,
        workspace_id: int,
        channel_id: str,
        ts: str,
    ) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT m.channel_id, c.name AS channel_name, m.ts, m.thread_ts, m.user_id,
                   u.username AS user_name,
                   u.display_name AS user_display_name,
                   COALESCE(u.display_name, u.real_name, u.username, m.user_id) AS user_label,
                   m.subtype, m.text, m.edited_ts, m.deleted, m.raw_json
            FROM messages m
            LEFT JOIN channels c ON c.workspace_id = m.workspace_id AND c.channel_id = m.channel_id
            LEFT JOIN users u ON u.workspace_id = m.workspace_id AND u.user_id = m.user_id
            WHERE m.workspace_id = ? AND m.channel_id = ? AND m.ts = ?
            LIMIT 1
            """,
            (workspace_id, channel_id, ts),
        ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["workspace"] = workspace
        return payload

    def _derived_text_context_pack_item(
        self,
        conn,
        *,
        target: dict[str, Any],
        before: int,
        after: int,
        include_text: bool,
        max_text_chars: int,
    ) -> dict[str, Any]:
        workspace = str(target.get("workspace") or "").strip()
        source_kind = str(target.get("source_kind") or "").strip()
        source_id = str(target.get("source_id") or "").strip()
        derivation_kind = str(target.get("derivation_kind") or "").strip()
        extractor = str(target.get("extractor") or "").strip() or None
        if not workspace or not source_kind or not source_id or not derivation_kind:
            return {"kind": "derived_text", "target": target, "resolved": False, "reason": "missing_derived_text_identity"}
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
            return {"kind": "derived_text", "target": target, "resolved": False, "reason": "derived_text_not_found"}
        chunks = get_derived_text_chunks(conn, derived_text_id=int(record["id"]))
        selected_chunk = _safe_int_or_none(target.get("chunk_index"))
        context_chunks = _select_context_chunks(
            chunks,
            selected_chunk=selected_chunk,
            before=before,
            after=after,
            include_text=include_text,
            max_text_chars=max_text_chars,
        )
        linked_messages = self._linked_messages_for_derived_text_source(
            conn,
            workspace=workspace,
            workspace_id=workspace_id,
            source_kind=source_kind,
            source_id=source_id,
            limit=max(1, before + after + 1),
            include_text=include_text,
            max_text_chars=max_text_chars,
        )
        return {
            "kind": "derived_text",
            "target": target,
            "resolved": True,
            "workspace": workspace,
            "workspace_id": workspace_id,
            "source": {
                "kind": source_kind,
                "id": source_id,
                "label": target.get("source_label") or source_id,
            },
            "derived_text": {
                "id": record.get("id"),
                "derivation_kind": record.get("derivation_kind"),
                "extractor": record.get("extractor"),
                "media_type": record.get("media_type"),
                "language_code": record.get("language_code"),
                "confidence": record.get("confidence"),
            },
            "context_chunks": context_chunks,
            "linked_messages": linked_messages,
        }

    def _linked_messages_for_derived_text_source(
        self,
        conn,
        *,
        workspace: str,
        workspace_id: int,
        source_kind: str,
        source_id: str,
        limit: int,
        include_text: bool,
        max_text_chars: int,
    ) -> list[dict[str, Any]]:
        if source_kind != "file":
            return []
        rows = conn.execute(
            """
            SELECT m.channel_id, c.name AS channel_name, m.ts, m.thread_ts, m.user_id,
                   COALESCE(u.display_name, u.real_name, u.username, m.user_id) AS user_label,
                   m.subtype, m.text, m.edited_ts, m.deleted
            FROM message_files mf
            JOIN messages m
              ON m.workspace_id = mf.workspace_id
             AND m.channel_id = mf.channel_id
             AND m.ts = mf.ts
            LEFT JOIN channels c ON c.workspace_id = m.workspace_id AND c.channel_id = m.channel_id
            LEFT JOIN users u ON u.workspace_id = m.workspace_id AND u.user_id = m.user_id
            WHERE mf.workspace_id = ? AND mf.file_id = ?
            ORDER BY CAST(m.ts AS REAL) ASC
            LIMIT ?
            """,
            (workspace_id, source_id, limit),
        ).fetchall()
        mention_ids: set[str] = set()
        for row in rows:
            mention_ids.update(slack_user_mention_ids(dict(row).get("text")))
        mention_labels = workspace_user_mention_labels(conn, workspace_id=workspace_id, user_ids=mention_ids)
        return [
            _project_context_message(
                row,
                workspace=workspace,
                relation="linked",
                selected=False,
                include_text=include_text,
                max_text_chars=max_text_chars,
                mention_labels=mention_labels,
            )
            for row in rows
        ]

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

    def normalize_channel_name(self, name: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(name or "").strip().lower())
        normalized = re.sub(r"-+", "-", normalized).strip("-_")
        if not normalized:
            raise ValueError("channel name is required")
        if len(normalized) > 80:
            raise ValueError("channel name must be 80 characters or fewer after normalization")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", normalized):
            raise ValueError(f"channel name is not Slack-compatible after normalization: {normalized}")
        return normalized

    def _find_channel_by_name(self, conn, *, workspace_id: int, name: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT channel_id, name, is_private, is_im, is_mpim, raw_json
            FROM channels
            WHERE workspace_id = ? AND lower(name) = lower(?)
            ORDER BY channel_id
            LIMIT 1
            """,
            (workspace_id, name),
        ).fetchone()
        return dict(row) if row else None

    def create_channel(
        self,
        conn,
        *,
        workspace: str,
        name: str,
        is_private: bool = False,
        invitees: list[str] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = dict(options or {})
        auth_mode = str(options.pop("auth_mode", "bot"))
        requested_name = str(name or "").strip()
        channel_name = self.normalize_channel_name(requested_name)
        workspace_id = self.workspace_id(conn, workspace)
        invitee_refs = [str(invitee).strip() for invitee in (invitees or []) if str(invitee).strip()]
        invited_user_ids: list[str] = []
        for invitee in invitee_refs:
            user_id = self.resolve_user_ref(conn, workspace_id, invitee)
            if not user_id:
                raise ValueError(f"User reference '{invitee}' was not found in workspace")
            invited_user_ids.append(user_id)

        existing = self._find_channel_by_name(conn, workspace_id=workspace_id, name=channel_name)
        created = False
        channel: dict[str, Any]
        if existing:
            if bool(existing.get("is_im")) or bool(existing.get("is_mpim")):
                raise ValueError(f"Existing conversation '{channel_name}' is not a channel")
            if bool(existing.get("is_private")) != bool(is_private):
                requested_kind = "private" if is_private else "public"
                existing_kind = "private" if existing.get("is_private") else "public"
                raise ValueError(
                    f"Existing channel '{channel_name}' is {existing_kind}; refusing to treat it as {requested_kind}"
                )
            try:
                raw = json.loads(str(existing.get("raw_json") or "{}"))
            except json.JSONDecodeError:
                raw = {}
            channel = raw if isinstance(raw, dict) else {}
            channel.setdefault("id", str(existing["channel_id"]))
            channel.setdefault("name", str(existing["name"]))
            channel.setdefault("is_private", bool(existing.get("is_private")))
        else:
            token = self.workspace_token(workspace, auth_mode=auth_mode, purpose="write")
            client = SlackApiClient(token)
            response = client.create_conversation(name=channel_name, is_private=bool(is_private))
            channel = dict(response.get("channel") or {})
            channel_id = str(channel.get("id") or "")
            if not channel_id:
                raise ValueError("Slack did not return a created channel id")
            db.upsert_channel(conn, workspace_id, channel)
            created = True

        channel_id = str(channel.get("id") or "")
        if not channel_id:
            raise ValueError("channel id is required")

        invite_response: dict[str, Any] | None = None
        if invited_user_ids:
            token = self.workspace_token(workspace, auth_mode=auth_mode, purpose="write")
            client = SlackApiClient(token)
            invite_response = client.invite_to_conversation(channel=channel_id, users=invited_user_ids)
            for user_id in invited_user_ids:
                db.upsert_channel_member(conn, workspace_id, channel_id, user_id)

        return {
            "workspace": workspace,
            "workspace_id": workspace_id,
            "requested_name": requested_name,
            "name": channel_name,
            "channel_id": channel_id,
            "is_private": bool(is_private),
            "created": created,
            "invited_user_ids": invited_user_ids,
            "invitees": invitee_refs,
            "channel": channel,
            "invite_response": invite_response,
            "auth_mode": auth_mode,
        }

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

    def list_conversations(
        self,
        conn,
        *,
        workspace: str | None = None,
        all_workspaces: bool = False,
        channel_type: str | None = None,
        name_query: str | None = None,
        member_query: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if all_workspaces and workspace:
            raise ValueError("workspace must not be set when all_workspaces is true")
        if not all_workspaces and not workspace:
            raise ValueError("workspace is required unless all_workspaces is true")
        allowed_types = {"public_channel", "private_channel", "im", "mpdm"}
        normalized_type = str(channel_type or "").strip().lower()
        if normalized_type and normalized_type not in allowed_types:
            raise ValueError(f"unsupported channel_type: {channel_type}")

        clauses: list[str] = []
        params: list[Any] = []
        if all_workspaces:
            names = self.enabled_workspace_names()
            if not names:
                return []
            placeholders = ", ".join("?" for _ in names)
            clauses.append(f"w.name IN ({placeholders})")
            params.extend(names)
        else:
            clauses.append("w.name = ?")
            params.append(str(workspace or "").strip())
        if normalized_type == "mpdm":
            clauses.append("c.is_mpim = 1")
        elif normalized_type == "im":
            clauses.append("c.is_im = 1")
        elif normalized_type == "private_channel":
            clauses.append("c.is_private = 1 AND c.is_im = 0 AND c.is_mpim = 0")
        elif normalized_type == "public_channel":
            clauses.append("c.is_private = 0 AND c.is_im = 0 AND c.is_mpim = 0")
        if str(name_query or "").strip():
            clauses.append("LOWER(COALESCE(c.name, c.channel_id, '')) LIKE ?")
            params.append(f"%{str(name_query).strip().lower()}%")
        where_sql = " AND ".join(clauses)
        member_filter = ""
        if str(member_query or "").strip():
            member_filter = """
            AND (
              LOWER(COALESCE(c.name, c.channel_id, '')) LIKE ?
              OR EXISTS (
                SELECT 1
                FROM channel_members cm_filter
                LEFT JOIN users u_filter
                  ON u_filter.workspace_id = cm_filter.workspace_id
                 AND u_filter.user_id = cm_filter.user_id
                WHERE cm_filter.workspace_id = c.workspace_id
                  AND cm_filter.channel_id = c.channel_id
                  AND LOWER(
                    COALESCE(u_filter.display_name, '') || ' ' ||
                    COALESCE(u_filter.real_name, '') || ' ' ||
                    COALESCE(u_filter.username, '') || ' ' ||
                    COALESCE(cm_filter.user_id, '')
                  ) LIKE ?
              )
            )
            """
            member_like = f"%{str(member_query).strip().lower()}%"
            params.extend([member_like, member_like])

        rows = conn.execute(
            f"""
            SELECT
              w.name AS workspace,
              w.id AS workspace_id,
              c.channel_id,
              c.name,
              c.is_private,
              c.is_im,
              c.is_mpim,
              c.topic,
              c.purpose,
              c.updated_at,
              COUNT(DISTINCT m.ts) AS message_count,
              MAX(CAST(m.ts AS REAL)) AS latest_ts_numeric,
              MAX(m.ts) AS latest_ts,
              COUNT(DISTINCT cm.user_id) AS member_count,
              GROUP_CONCAT(
                DISTINCT COALESCE(u.display_name, u.real_name, u.username, cm.user_id)
              ) AS member_labels
            FROM channels c
            JOIN workspaces w ON w.id = c.workspace_id
            LEFT JOIN messages m
              ON m.workspace_id = c.workspace_id
             AND m.channel_id = c.channel_id
            LEFT JOIN channel_members cm
              ON cm.workspace_id = c.workspace_id
             AND cm.channel_id = c.channel_id
            LEFT JOIN users u
              ON u.workspace_id = cm.workspace_id
             AND u.user_id = cm.user_id
            WHERE {where_sql}
            {member_filter}
            GROUP BY w.name, w.id, c.channel_id
            ORDER BY latest_ts_numeric IS NULL ASC, latest_ts_numeric DESC, message_count DESC, c.name ASC
            LIMIT ?
            """,
            tuple([*params, max(1, min(int(limit or 50), 200))]),
        ).fetchall()

        conversations: list[dict[str, Any]] = []
        for row_obj in rows:
            row = dict(row_obj)
            if row.get("is_mpim"):
                row_type = "mpdm"
            elif row.get("is_im"):
                row_type = "im"
            elif row.get("is_private"):
                row_type = "private_channel"
            else:
                row_type = "public_channel"
            member_labels = [
                part.strip()
                for part in str(row.get("member_labels") or "").split(",")
                if part.strip()
            ]
            latest_ts = str(row.get("latest_ts") or "").strip() or None
            conversations.append(
                {
                    "workspace": row.get("workspace"),
                    "workspace_id": row.get("workspace_id"),
                    "channel_id": row.get("channel_id"),
                    "name": row.get("name") or row.get("channel_id"),
                    "conversation_type": row_type,
                    "is_private": bool(row.get("is_private")),
                    "is_im": bool(row.get("is_im")),
                    "is_mpim": bool(row.get("is_mpim")),
                    "message_count": int(row.get("message_count") or 0),
                    "latest_ts": latest_ts,
                    "latest_at": _slack_ts_to_iso(latest_ts),
                    "member_count": int(row.get("member_count") or 0),
                    "member_labels": member_labels,
                    "topic": row.get("topic"),
                    "purpose": row.get("purpose"),
                }
            )
        return conversations

    def _corpus_profile_search_options(self, profile_name: str) -> dict[str, Any]:
        profile = self.retrieval_profile(profile_name)
        profile_config = self.config_for_retrieval_profile(profile)
        return {
            "mode": profile.mode,
            "model_id": profile.model,
            "lexical_weight": profile.lexical_weight,
            "semantic_weight": profile.semantic_weight,
            "semantic_scale": profile.semantic_scale,
            "rerank": profile.rerank,
            "rerank_top_n": profile.rerank_top_n,
            "message_embedding_provider": build_embedding_provider(profile_config),
            "reranker_provider": build_reranker_provider(profile_config) if profile.rerank else None,
        }

    def corpus_search(
        self,
        conn,
        *,
        workspace: str | None = None,
        all_workspaces: bool = False,
        query: str,
        retrieval_profile_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
        mode: str = "hybrid",
        model_id: str = "local-hash-128",
        lexical_weight: float = 0.6,
        semantic_weight: float = 0.4,
        semantic_scale: float = 10.0,
        fusion_method: str = "weighted",
        use_fts: bool = True,
        derived_kind: str | None = None,
        derived_source_kind: str | None = None,
        message_embedding_provider=None,
        rerank: bool = False,
        rerank_top_n: int = 50,
        reranker_provider=None,
    ) -> list[dict[str, Any]]:
        if retrieval_profile_name:
            profile_options = self._corpus_profile_search_options(retrieval_profile_name)
            mode = profile_options["mode"]
            model_id = profile_options["model_id"]
            lexical_weight = profile_options["lexical_weight"]
            semantic_weight = profile_options["semantic_weight"]
            semantic_scale = profile_options["semantic_scale"]
            rerank = profile_options["rerank"]
            rerank_top_n = profile_options["rerank_top_n"]
            message_embedding_provider = profile_options["message_embedding_provider"]
            reranker_provider = profile_options["reranker_provider"]

        provider = message_embedding_provider or self.message_embedding_provider()
        active_reranker_provider = (reranker_provider or self.reranker_provider()) if rerank else None
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
                fusion_method=fusion_method,
                use_fts=use_fts,
                derived_kind=derived_kind,
                derived_source_kind=derived_source_kind,
                message_embedding_provider=provider,
                rerank=rerank,
                rerank_top_n=rerank_top_n,
                reranker_provider=active_reranker_provider,
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
            fusion_method=fusion_method,
            use_fts=use_fts,
            derived_kind=derived_kind,
            derived_source_kind=derived_source_kind,
            message_embedding_provider=provider,
            rerank=rerank,
            rerank_top_n=rerank_top_n,
            reranker_provider=active_reranker_provider,
        )

    def corpus_search_page(
        self,
        conn,
        *,
        workspace: str | None = None,
        all_workspaces: bool = False,
        query: str,
        retrieval_profile_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
        mode: str = "hybrid",
        model_id: str = "local-hash-128",
        lexical_weight: float = 0.6,
        semantic_weight: float = 0.4,
        semantic_scale: float = 10.0,
        fusion_method: str = "weighted",
        use_fts: bool = True,
        derived_kind: str | None = None,
        derived_source_kind: str | None = None,
        message_embedding_provider=None,
        rerank: bool = False,
        rerank_top_n: int = 50,
        reranker_provider=None,
    ) -> dict[str, Any]:
        if retrieval_profile_name:
            profile_options = self._corpus_profile_search_options(retrieval_profile_name)
            mode = profile_options["mode"]
            model_id = profile_options["model_id"]
            lexical_weight = profile_options["lexical_weight"]
            semantic_weight = profile_options["semantic_weight"]
            semantic_scale = profile_options["semantic_scale"]
            rerank = profile_options["rerank"]
            rerank_top_n = profile_options["rerank_top_n"]
            message_embedding_provider = profile_options["message_embedding_provider"]
            reranker_provider = profile_options["reranker_provider"]

        provider = message_embedding_provider or self.message_embedding_provider()
        active_reranker_provider = (reranker_provider or self.reranker_provider()) if rerank else None
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
                fusion_method=fusion_method,
                use_fts=use_fts,
                derived_kind=derived_kind,
                derived_source_kind=derived_source_kind,
                message_embedding_provider=provider,
                rerank=rerank,
                rerank_top_n=rerank_top_n,
                reranker_provider=active_reranker_provider,
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
            fusion_method=fusion_method,
            use_fts=use_fts,
            derived_kind=derived_kind,
            derived_source_kind=derived_source_kind,
            message_embedding_provider=provider,
            rerank=rerank,
            rerank_top_n=rerank_top_n,
            reranker_provider=active_reranker_provider,
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

    def semantic_rollout_plan(
        self,
        conn,
        *,
        workspace: str,
        profile_name: str,
        limit: int = 500,
        channels: list[str] | None = None,
        oldest: str | None = None,
        latest: str | None = None,
        derived_kind: str | None = None,
        derived_source_kind: str | None = None,
    ) -> dict[str, Any]:
        workspace_id = self.workspace_id(conn, workspace)
        profile = self.retrieval_profile(profile_name)
        model = profile.model
        channel_ids = [value.strip() for value in (channels or []) if value.strip()]

        message_where = ["m.workspace_id = ?", "m.deleted = 0"]
        message_params: list[Any] = [workspace_id]
        if channel_ids:
            message_where.append("m.channel_id IN (" + ",".join("?" for _ in channel_ids) + ")")
            message_params.extend(channel_ids)
        if oldest:
            message_where.append("CAST(m.ts AS REAL) >= CAST(? AS REAL)")
            message_params.append(oldest)
        if latest:
            message_where.append("CAST(m.ts AS REAL) <= CAST(? AS REAL)")
            message_params.append(latest)
        message_where_sql = " AND ".join(message_where)
        message_total = int(
            conn.execute(
                f"SELECT COUNT(*) AS c FROM messages m WHERE {message_where_sql}",
                tuple(message_params),
            ).fetchone()["c"]
        )
        message_embedded = int(
            conn.execute(
                f"""
                SELECT COUNT(*) AS c
                FROM messages m
                JOIN message_embeddings me
                  ON me.workspace_id = m.workspace_id
                 AND me.channel_id = m.channel_id
                 AND me.ts = m.ts
                 AND me.model_id = ?
                WHERE {message_where_sql}
                """,
                tuple([model, *message_params]),
            ).fetchone()["c"]
        )

        derived_where = ["dc.workspace_id = ?"]
        derived_params: list[Any] = [workspace_id]
        if derived_kind:
            derived_where.append("dt.derivation_kind = ?")
            derived_params.append(derived_kind)
        if derived_source_kind:
            derived_where.append("dt.source_kind = ?")
            derived_params.append(derived_source_kind)
        derived_where_sql = " AND ".join(derived_where)
        derived_total = int(
            conn.execute(
                f"""
                SELECT COUNT(*) AS c
                FROM derived_text_chunks dc
                JOIN derived_text dt ON dt.id = dc.derived_text_id
                WHERE {derived_where_sql}
                """,
                tuple(derived_params),
            ).fetchone()["c"]
        )
        derived_embedded = int(
            conn.execute(
                f"""
                SELECT COUNT(*) AS c
                FROM derived_text_chunks dc
                JOIN derived_text dt ON dt.id = dc.derived_text_id
                JOIN derived_text_chunk_embeddings dte
                  ON dte.derived_text_chunk_id = dc.id
                 AND dte.model_id = ?
                WHERE {derived_where_sql}
                """,
                tuple([model, *derived_params]),
            ).fetchone()["c"]
        )

        config_arg = str(self.config.path)
        message_command = [
            "slack-mirror",
            "--config",
            config_arg,
            "mirror",
            "embeddings-backfill",
            "--workspace",
            workspace,
            "--retrieval-profile",
            profile.name,
            "--model",
            model,
            "--limit",
            str(int(limit)),
            "--json",
        ]
        if channel_ids:
            message_command.extend(["--channels", ",".join(channel_ids)])
        if oldest:
            message_command.extend(["--oldest", oldest])
        if latest:
            message_command.extend(["--latest", latest])

        derived_command = [
            "slack-mirror",
            "--config",
            config_arg,
            "mirror",
            "derived-text-embeddings-backfill",
            "--workspace",
            workspace,
            "--retrieval-profile",
            profile.name,
            "--model",
            model,
            "--limit",
            str(int(limit)),
            "--json",
        ]
        if derived_kind:
            derived_command.extend(["--kind", derived_kind])
        if derived_source_kind:
            derived_command.extend(["--source-kind", derived_source_kind])

        commands = {
            "provider_probe": [
                "slack-mirror",
                "--config",
                config_arg,
                "search",
                "provider-probe",
                "--retrieval-profile",
                profile.name,
                "--smoke",
                "--json",
            ],
            "message_embeddings_backfill": message_command,
            "derived_text_embeddings_backfill": derived_command,
            "search_health": [
                "slack-mirror",
                "--config",
                config_arg,
                "search",
                "health",
                "--workspace",
                workspace,
                "--retrieval-profile",
                profile.name,
                "--json",
            ],
        }
        if profile.rerank:
            commands["reranker_probe"] = [
                "slack-mirror",
                "--config",
                config_arg,
                "search",
                "reranker-probe",
                "--retrieval-profile",
                profile.name,
                "--smoke",
                "--json",
            ]

        return {
            "workspace": workspace,
            "profile": profile.to_dict(),
            "filters": {
                "limit": int(limit),
                "channels": channel_ids,
                "oldest": oldest,
                "latest": latest,
                "derived_kind": derived_kind,
                "derived_source_kind": derived_source_kind,
            },
            "coverage": {
                "messages": _coverage_payload(message_total, message_embedded),
                "derived_text_chunks": _coverage_payload(derived_total, derived_embedded),
            },
            "commands": commands,
            "status": "ready" if message_embedded >= message_total and derived_embedded >= derived_total else "rollout_needed",
        }

    def semantic_readiness(
        self,
        conn,
        *,
        workspace: str | None = None,
        profile_names: list[str] | None = None,
        include_commands: bool = False,
        command_limit: int = 500,
    ) -> dict[str, Any]:
        workspaces = [workspace] if workspace else self.enabled_workspace_names()
        profiles = (
            [self.retrieval_profile(name) for name in profile_names]
            if profile_names
            else [self.retrieval_profile(str(profile["name"])) for profile in self.retrieval_profiles()]
        )

        active_semantic = dict((self.config.get("search", {}) or {}).get("semantic", {}) or {})
        active_rerank = dict((self.config.get("search", {}) or {}).get("rerank", {}) or {})
        active_config = {
            "mode": str(active_semantic.get("mode_default") or "hybrid"),
            "model": str(active_semantic.get("model") or "local-hash-128"),
            "semantic_provider": dict(active_semantic.get("provider") or {}),
            "rerank_provider": dict(active_rerank.get("provider") or {}),
        }

        workspace_payloads: list[dict[str, Any]] = []
        for workspace_name in workspaces:
            profile_payloads: list[dict[str, Any]] = []
            for profile in profiles:
                profile_config = self.config_for_retrieval_profile(profile)
                provider_probe = probe_embedding_provider(profile_config, model_id=profile.model)
                reranker_probe = probe_reranker_provider(profile_config) if profile.rerank else None
                plan = self.semantic_rollout_plan(
                    conn,
                    workspace=workspace_name,
                    profile_name=profile.name,
                    limit=command_limit,
                )
                profile_state = _semantic_profile_state(
                    plan=plan,
                    provider_probe=provider_probe,
                    reranker_probe=reranker_probe,
                )
                profile_payload: dict[str, Any] = {
                    "name": profile.name,
                    "description": profile.description,
                    "experimental": profile.experimental,
                    "mode": profile.mode,
                    "model": profile.model,
                    "semantic_provider": profile.semantic_provider,
                    "rerank": profile.rerank,
                    "rerank_top_n": profile.rerank_top_n,
                    "rerank_provider": profile.rerank_provider,
                    "state": profile_state["state"],
                    "tone": profile_state["tone"],
                    "summary": profile_state["summary"],
                    "provider_available": bool(provider_probe.get("available")),
                    "provider_issues": list(provider_probe.get("issues") or []),
                    "reranker_available": None if reranker_probe is None else bool(reranker_probe.get("available")),
                    "reranker_issues": [] if reranker_probe is None else list(reranker_probe.get("issues") or []),
                    "coverage": plan["coverage"],
                    "commands": plan["commands"] if include_commands else None,
                }
                profile_payloads.append(profile_payload)

            workspace_status = _semantic_workspace_state(profile_payloads)
            workspace_payloads.append(
                {
                    "workspace": workspace_name,
                    "status": workspace_status["state"],
                    "tone": workspace_status["tone"],
                    "summary": workspace_status["summary"],
                    "active_config": active_config,
                    "profiles": profile_payloads,
                }
            )

        return {
            "scope": "workspace" if workspace else "all",
            "workspace": workspace,
            "profiles": [profile.to_dict() for profile in profiles],
            "workspaces": workspace_payloads,
        }

    def search_scale_review(
        self,
        conn,
        *,
        workspace: str,
        queries: list[str] | None = None,
        profile_names: list[str] | None = None,
        repeats: int = 3,
        limit: int = 10,
        fusion_method: str = "weighted",
    ) -> dict[str, Any]:
        if repeats < 1:
            raise ValueError("repeats must be at least 1")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        query_values = [value.strip() for value in (queries or ["incident review"]) if value.strip()]
        if not query_values:
            raise ValueError("at least one non-empty query is required")
        profiles = (
            [self.retrieval_profile(name) for name in profile_names]
            if profile_names
            else [self.retrieval_profile("baseline")]
        )
        workspace_id = self.workspace_id(conn, workspace)
        corpus = self._search_scale_corpus_stats(conn, workspace_id=workspace_id)

        runs: list[dict[str, Any]] = []
        for profile in profiles:
            profile_config = self.config_for_retrieval_profile(profile)
            embedding_provider = build_embedding_provider(profile_config)
            reranker_provider = build_reranker_provider(profile_config) if profile.rerank else None
            weights = dict(profile.weights or {})
            lexical_weight = float(weights.get("lexical", 0.6))
            semantic_weight = float(weights.get("semantic", 0.4))
            semantic_scale = float(weights.get("semantic_scale", 10.0))
            for query in query_values:
                latencies: list[float] = []
                result_counts: list[int] = []
                for _ in range(int(repeats)):
                    started = time.perf_counter()
                    rows = self.corpus_search(
                        conn,
                        workspace=workspace,
                        query=query,
                        limit=int(limit),
                        mode=profile.mode,
                        model_id=profile.model,
                        lexical_weight=lexical_weight,
                        semantic_weight=semantic_weight,
                        semantic_scale=semantic_scale,
                        fusion_method=fusion_method,
                        message_embedding_provider=embedding_provider,
                        rerank=bool(profile.rerank),
                        rerank_top_n=int(profile.rerank_top_n),
                        reranker_provider=reranker_provider,
                    )
                    latencies.append(round((time.perf_counter() - started) * 1000.0, 3))
                    result_counts.append(len(rows))
                runs.append(
                    {
                        "profile": profile.name,
                        "query": query,
                        "mode": profile.mode,
                        "model": profile.model,
                        "fusion_method": fusion_method,
                        "rerank": bool(profile.rerank),
                        "rerank_provider": None if not profile.rerank else dict(profile.rerank_provider or {}),
                        "repeats": int(repeats),
                        "limit": int(limit),
                        "latency_ms": _latency_summary(latencies),
                        "result_counts": result_counts,
                    }
                )

        return {
            "workspace": workspace,
            "workspace_id": workspace_id,
            "queries": query_values,
            "profiles": [profile.to_dict() for profile in profiles],
            "corpus": corpus,
            "runs": runs,
            "decision": _search_scale_decision(corpus, runs),
        }

    def benchmark_dataset_report(
        self,
        conn,
        *,
        workspace: str,
        dataset_path: str,
        profile_names: list[str] | None = None,
    ) -> dict[str, Any]:
        workspace_id = self.workspace_id(conn, workspace)
        rows = dataset_rows(dataset_path)
        profiles = [self.retrieval_profile(name) for name in (profile_names or ["baseline"])]
        model_ids: list[str] = []
        for profile in profiles:
            if profile.model not in model_ids:
                model_ids.append(profile.model)

        query_reports: list[dict[str, Any]] = []
        unresolved_labels: list[dict[str, Any]] = []
        ambiguous_labels: list[dict[str, Any]] = []
        resolved_label_count = 0
        label_count = 0
        coverage_by_model = {
            model_id: {
                "labels": 0,
                "covered": 0,
                "messages": 0,
                "message_covered": 0,
                "derived_text": 0,
                "derived_text_covered": 0,
            }
            for model_id in model_ids
        }

        for index, row in enumerate(rows, start=1):
            relevant = dict(row.get("relevant") or {})
            row_labels = []
            for label, weight in relevant.items():
                label_count += 1
                matches = self._resolve_benchmark_label(conn, workspace_id=workspace_id, label=str(label))
                if not matches:
                    unresolved_labels.append({"query_index": index, "label": label})
                    row_labels.append({"label": label, "resolved": False, "ambiguous": False, "weight": weight})
                    continue
                if len(matches) > 1:
                    ambiguous_labels.append({"query_index": index, "label": label, "matches": len(matches)})
                match = matches[0]
                resolved_label_count += 1
                label_report = {
                    "label": label,
                    "resolved": True,
                    "ambiguous": len(matches) > 1,
                    "kind": match["kind"],
                    "weight": weight,
                    "coverage": {},
                }
                for model_id in model_ids:
                    covered = self._benchmark_label_model_covered(
                        conn,
                        workspace_id=workspace_id,
                        match=match,
                        model_id=model_id,
                    )
                    coverage = coverage_by_model[model_id]
                    coverage["labels"] += 1
                    coverage["covered"] += 1 if covered else 0
                    if match["kind"] == "message":
                        coverage["messages"] += 1
                        coverage["message_covered"] += 1 if covered else 0
                    elif match["kind"] == "derived_text":
                        coverage["derived_text"] += 1
                        coverage["derived_text_covered"] += 1 if covered else 0
                    label_report["coverage"][model_id] = covered
                row_labels.append(label_report)
            query_reports.append(
                {
                    "index": index,
                    "id": row.get("id"),
                    "intent": row.get("intent"),
                    "query": row.get("query"),
                    "labels": row_labels,
                }
            )

        profile_reports = []
        for profile in profiles:
            coverage = dict(coverage_by_model.get(profile.model) or {})
            labels = int(coverage.get("labels", 0) or 0)
            covered = int(coverage.get("covered", 0) or 0)
            coverage["coverage_ratio"] = round(covered / labels, 6) if labels else 0.0
            profile_reports.append(
                {
                    "name": profile.name,
                    "model": profile.model,
                    "mode": profile.mode,
                    "rerank": profile.rerank,
                    "coverage": coverage,
                }
            )

        status = "pass"
        if unresolved_labels:
            status = "fail"
        elif ambiguous_labels or any(profile["coverage"]["coverage_ratio"] < 1.0 for profile in profile_reports):
            status = "pass_with_warnings"

        return {
            "workspace": workspace,
            "dataset_path": dataset_path,
            "status": status,
            "queries": len(rows),
            "labels": label_count,
            "resolved_labels": resolved_label_count,
            "unresolved_labels": unresolved_labels,
            "ambiguous_labels": ambiguous_labels,
            "profiles": profile_reports,
            "query_reports": query_reports,
        }

    def benchmark_profile_diagnostics(
        self,
        conn,
        *,
        workspace: str,
        dataset_path: str,
        profile_names: list[str] | None = None,
        limit: int = 10,
        fusion_method: str = "weighted",
        include_text: bool = False,
    ) -> dict[str, Any]:
        workspace_id = self.workspace_id(conn, workspace)
        rows = dataset_rows(dataset_path)
        profiles = [self.retrieval_profile(name) for name in (profile_names or ["baseline"])]
        profile_payloads = [profile.to_dict() for profile in profiles]
        profile_contexts = []
        for profile in profiles:
            profile_config = self.config_for_retrieval_profile(profile)
            profile_contexts.append(
                {
                    "profile": profile,
                    "embedding_provider": build_embedding_provider(profile_config),
                    "reranker_provider": build_reranker_provider(profile_config) if profile.rerank else None,
                }
            )

        query_reports: list[dict[str, Any]] = []
        unresolved_labels: list[dict[str, Any]] = []
        ambiguous_labels: list[dict[str, Any]] = []

        for index, row in enumerate(rows, start=1):
            relevant = dict(row.get("relevant") or {})
            expected_targets: list[dict[str, Any]] = []
            for label, weight in relevant.items():
                matches = self._resolve_benchmark_label(conn, workspace_id=workspace_id, label=str(label))
                if not matches:
                    unresolved_labels.append({"query_index": index, "label": label})
                if len(matches) > 1:
                    ambiguous_labels.append({"query_index": index, "label": label, "matches": len(matches)})
                expected_targets.append(
                    {
                        "label": str(label),
                        "weight": weight,
                        "resolved": bool(matches),
                        "ambiguous": len(matches) > 1,
                        "evidence": self._benchmark_target_evidence(
                            conn,
                            workspace_id=workspace_id,
                            query=str(row.get("query") or ""),
                            matches=matches,
                        ),
                        "matches": [self._benchmark_match_identity(match) for match in matches],
                    }
                )

            profile_runs: list[dict[str, Any]] = []
            baseline_ranks: dict[str, int | None] = {}
            for profile_index, profile_context in enumerate(profile_contexts):
                profile = profile_context["profile"]
                started = time.perf_counter()
                result_rows = self.corpus_search(
                    conn,
                    workspace=workspace,
                    query=str(row.get("query") or ""),
                    limit=int(limit),
                    mode=profile.mode,
                    model_id=profile.model,
                    lexical_weight=profile.lexical_weight,
                    semantic_weight=profile.semantic_weight,
                    semantic_scale=profile.semantic_scale,
                    fusion_method=fusion_method,
                    message_embedding_provider=profile_context["embedding_provider"],
                    rerank=bool(profile.rerank),
                    rerank_top_n=int(profile.rerank_top_n),
                    reranker_provider=profile_context["reranker_provider"],
                )
                latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
                top_results = [
                    self._benchmark_result_diagnostic(result, rank=rank, include_text=include_text)
                    for rank, result in enumerate(result_rows, start=1)
                ]
                source_counts: dict[str, int] = {}
                for result in top_results:
                    source = str(result.get("explain", {}).get("source") or result.get("kind") or "unknown")
                    source_counts[source] = source_counts.get(source, 0) + 1

                target_reports: list[dict[str, Any]] = []
                for target in expected_targets:
                    labels = {
                        value
                        for match in target["matches"]
                        for value in list(match.get("labels") or [])
                        if value
                    }
                    rank = None
                    matched_result = None
                    for result in top_results:
                        if labels.intersection(set(result.get("labels") or [])):
                            rank = int(result["rank"])
                            matched_result = result
                            break
                    if profile_index == 0:
                        baseline_ranks[target["label"]] = rank
                    baseline_rank = baseline_ranks.get(target["label"])
                    target_reports.append(
                        {
                            "label": target["label"],
                            "weight": target["weight"],
                            "resolved": target["resolved"],
                            "ambiguous": target["ambiguous"],
                            "evidence": target.get("evidence"),
                            "rank": rank,
                            "hit_at_3": rank is not None and rank <= 3,
                            "hit_at_10": rank is not None and rank <= 10,
                            "baseline_rank": baseline_rank,
                            "rank_delta_vs_baseline": None
                            if baseline_rank is None or rank is None
                            else int(rank) - int(baseline_rank),
                            "movement_vs_baseline": _rank_movement(baseline_rank, rank),
                            "matched_result": matched_result,
                        }
                    )

                profile_runs.append(
                    {
                        "profile": profile.name,
                        "mode": profile.mode,
                        "model": profile.model,
                        "rerank": bool(profile.rerank),
                        "latency_ms": latency_ms,
                        "source_counts": source_counts,
                        "expected_targets": target_reports,
                        "top_results": top_results,
                    }
                )

            query_reports.append(
                {
                    "index": index,
                    "id": row.get("id"),
                    "intent": row.get("intent"),
                    "query": row.get("query"),
                    "expected_targets": expected_targets,
                    "profiles": profile_runs,
                }
            )

        status = "pass"
        if unresolved_labels:
            status = "fail"
        elif ambiguous_labels:
            status = "pass_with_warnings"

        return {
            "workspace": workspace,
            "workspace_id": workspace_id,
            "dataset_path": dataset_path,
            "status": status,
            "queries": len(rows),
            "limit": int(limit),
            "fusion_method": fusion_method,
            "profiles": profile_payloads,
            "include_text": bool(include_text),
            "unresolved_labels": unresolved_labels,
            "ambiguous_labels": ambiguous_labels,
            "query_reports": query_reports,
        }

    def benchmark_query_variants(
        self,
        conn,
        *,
        workspace: str,
        dataset_path: str,
        profile_names: list[str] | None = None,
        variant_names: list[str] | None = None,
        mode: str | None = None,
        limit: int = 10,
        fusion_method: str = "weighted",
        model_id: str | None = None,
        include_details: bool = False,
    ) -> dict[str, Any]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        workspace_id = self.workspace_id(conn, workspace)
        rows = dataset_rows(dataset_path)
        profiles = [self.retrieval_profile(name) for name in (profile_names or ["baseline"])]
        variants = [value.strip() for value in (variant_names or ["original", "lowercase", "dehyphen", "alnum"]) if value.strip()]
        if not variants:
            raise ValueError("at least one query variant is required")

        runs: list[dict[str, Any]] = []
        for profile in profiles:
            profile_config = self.config_for_retrieval_profile(profile)
            embedding_provider = build_embedding_provider(profile_config)
            reranker_provider = build_reranker_provider(profile_config) if profile.rerank else None
            for variant in variants:
                benchmark = evaluate_corpus_search(
                    conn,
                    workspace_id=workspace_id,
                    dataset=_variant_dataset_rows(rows, variant),
                    mode=mode or profile.mode,
                    limit=limit,
                    model_id=model_id or profile.model,
                    fusion_method=fusion_method,
                    lexical_weight=profile.lexical_weight,
                    semantic_weight=profile.semantic_weight,
                    semantic_scale=profile.semantic_scale,
                    embedding_provider=embedding_provider,
                    rerank=bool(profile.rerank),
                    rerank_top_n=int(profile.rerank_top_n),
                    reranker_provider=reranker_provider,
                )
                query_reports = list(benchmark.pop("query_reports", []) or [])
                metrics = {
                    "queries": benchmark.get("queries", 0),
                    "hit_at_3": benchmark.get("hit_at_3"),
                    "hit_at_10": benchmark.get("hit_at_10"),
                    "ndcg_at_k": benchmark.get("ndcg_at_k"),
                    "mrr_at_k": benchmark.get("mrr_at_k"),
                    "latency_ms_p50": benchmark.get("latency_ms_p50"),
                    "latency_ms_p95": benchmark.get("latency_ms_p95"),
                }
                run: dict[str, Any] = {
                    "profile": profile.name,
                    "variant": variant,
                    "variant_definition": _variant_definition(variant),
                    "mode": benchmark.get("mode") or mode or profile.mode,
                    "model": model_id or profile.model,
                    "fusion_method": benchmark.get("fusion_method") or fusion_method,
                    "weights": benchmark.get("weights"),
                    "rerank": bool(profile.rerank),
                    "rerank_provider": None if not profile.rerank else dict(profile.rerank_provider or {}),
                    "metrics": metrics,
                }
                if include_details:
                    run["query_reports"] = query_reports
                runs.append(run)

        best = _best_query_variant_run(runs)
        return {
            "workspace": workspace,
            "workspace_id": workspace_id,
            "dataset_path": dataset_path,
            "queries": len(rows),
            "limit": int(limit),
            "fusion_method": fusion_method,
            "profiles": [profile.to_dict() for profile in profiles],
            "variants": [_variant_definition(variant) for variant in variants],
            "include_details": bool(include_details),
            "status": "pass",
            "runs": runs,
            "best_run": None
            if best is None
            else {
                "profile": best.get("profile"),
                "variant": best.get("variant"),
                "metrics": best.get("metrics"),
            },
        }

    def backfill_benchmark_dataset_embeddings(
        self,
        conn,
        *,
        workspace: str,
        dataset_path: str,
        retrieval_profile_name: str,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        from slack_mirror.sync.derived_text import backfill_derived_text_chunk_embeddings_for_targets
        from slack_mirror.sync.embeddings import backfill_message_embeddings_for_targets

        workspace_id = self.workspace_id(conn, workspace)
        rows = dataset_rows(dataset_path)
        profile = self.retrieval_profile(retrieval_profile_name)
        profile_config = self.config_for_retrieval_profile(profile)
        active_model_id = model_id or profile.model
        embedding_provider = build_embedding_provider(profile_config)

        message_targets: list[dict[str, str]] = []
        derived_text_ids: list[int] = []
        unresolved_labels: list[dict[str, Any]] = []
        ambiguous_labels: list[dict[str, Any]] = []
        label_count = 0

        for index, row in enumerate(rows, start=1):
            for label in dict(row.get("relevant") or {}).keys():
                label_count += 1
                matches = self._resolve_benchmark_label(conn, workspace_id=workspace_id, label=str(label))
                if not matches:
                    unresolved_labels.append({"query_index": index, "label": label})
                    continue
                if len(matches) > 1:
                    ambiguous_labels.append({"query_index": index, "label": label, "matches": len(matches)})
                for match in matches:
                    if match["kind"] == "message":
                        message_targets.append({"channel_id": str(match["channel_id"]), "ts": str(match["ts"])})
                    elif match["kind"] == "derived_text":
                        derived_text_ids.append(int(match["derived_text_id"]))

        message_result = backfill_message_embeddings_for_targets(
            conn,
            workspace_id=workspace_id,
            targets=message_targets,
            model_id=active_model_id,
            provider=embedding_provider,
        )
        derived_result = backfill_derived_text_chunk_embeddings_for_targets(
            conn,
            workspace_id=workspace_id,
            derived_text_ids=derived_text_ids,
            model_id=active_model_id,
            provider=embedding_provider,
        )
        status = "pass" if not unresolved_labels else "fail"
        if status == "pass" and ambiguous_labels:
            status = "pass_with_warnings"
        return {
            "workspace": workspace,
            "workspace_id": workspace_id,
            "dataset_path": dataset_path,
            "retrieval_profile": profile.to_dict(),
            "model": active_model_id,
            "provider": getattr(embedding_provider, "name", embedding_provider.__class__.__name__),
            "status": status,
            "queries": len(rows),
            "labels": label_count,
            "message_targets": len({(target["channel_id"], target["ts"]) for target in message_targets}),
            "derived_text_targets": len(set(derived_text_ids)),
            "unresolved_labels": unresolved_labels,
            "ambiguous_labels": ambiguous_labels,
            "messages": message_result,
            "derived_text_chunks": derived_result,
        }

    def _resolve_benchmark_label(self, conn, *, workspace_id: int, label: str) -> list[dict[str, Any]]:
        parts = label.split(":")
        if len(parts) == 2:
            channel_key, ts = parts
            rows = conn.execute(
                """
                SELECT m.channel_id, c.name AS channel_name, m.ts
                FROM messages m
                LEFT JOIN channels c
                  ON c.workspace_id = m.workspace_id
                 AND c.channel_id = m.channel_id
                WHERE m.workspace_id = ?
                  AND m.ts = ?
                  AND (m.channel_id = ? OR c.name = ?)
                """,
                (workspace_id, ts, channel_key, channel_key),
            ).fetchall()
            return [
                {"kind": "message", "channel_id": row["channel_id"], "channel_name": row["channel_name"], "ts": row["ts"]}
                for row in rows
            ]
        if len(parts) == 4:
            source_kind, source_id, derivation_kind, extractor = parts
            rows = conn.execute(
                """
                SELECT id, source_kind, source_id, derivation_kind, extractor
                FROM derived_text
                WHERE workspace_id = ?
                  AND source_kind = ?
                  AND source_id = ?
                  AND derivation_kind = ?
                  AND extractor = ?
                """,
                (workspace_id, source_kind, source_id, derivation_kind, extractor),
            ).fetchall()
            return [
                {
                    "kind": "derived_text",
                    "derived_text_id": row["id"],
                    "source_kind": row["source_kind"],
                    "source_id": row["source_id"],
                    "derivation_kind": row["derivation_kind"],
                    "extractor": row["extractor"],
                }
                for row in rows
            ]

        rows = conn.execute(
            """
            SELECT dt.id, dt.source_kind, dt.source_id, dt.derivation_kind, dt.extractor
            FROM derived_text dt
            LEFT JOIN files f
              ON dt.source_kind = 'file'
             AND f.workspace_id = dt.workspace_id
             AND f.file_id = dt.source_id
            LEFT JOIN canvases c
              ON dt.source_kind = 'canvas'
             AND c.workspace_id = dt.workspace_id
             AND c.canvas_id = dt.source_id
            WHERE dt.workspace_id = ?
              AND COALESCE(f.title, f.name, c.title, dt.source_id) = ?
            """,
            (workspace_id, label),
        ).fetchall()
        return [
            {
                "kind": "derived_text",
                "derived_text_id": row["id"],
                "source_kind": row["source_kind"],
                "source_id": row["source_id"],
                "derivation_kind": row["derivation_kind"],
                "extractor": row["extractor"],
            }
            for row in rows
        ]

    def _benchmark_match_identity(self, match: dict[str, Any]) -> dict[str, Any]:
        if match["kind"] == "message":
            labels = [f"{match.get('channel_id')}:{match.get('ts')}"]
            if match.get("channel_name"):
                labels.append(f"{match.get('channel_name')}:{match.get('ts')}")
            return {
                "kind": "message",
                "channel_id": match.get("channel_id"),
                "channel_name": match.get("channel_name"),
                "ts": match.get("ts"),
                "labels": labels,
            }
        if match["kind"] == "derived_text":
            labels = [
                f"{match.get('source_kind')}:{match.get('source_id')}:"
                f"{match.get('derivation_kind')}:{match.get('extractor')}"
            ]
            return {
                "kind": "derived_text",
                "derived_text_id": match.get("derived_text_id"),
                "source_kind": match.get("source_kind"),
                "source_id": match.get("source_id"),
                "derivation_kind": match.get("derivation_kind"),
                "extractor": match.get("extractor"),
                "labels": labels,
            }
        return {"kind": match.get("kind"), "labels": []}

    def _benchmark_target_evidence(
        self,
        conn,
        *,
        workspace_id: int,
        query: str,
        matches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        query_terms = sorted(set(re.findall(r"[a-z0-9]+", str(query or "").lower())))
        if not query_terms:
            return {
                "query_terms": [],
                "resolved_targets": len(matches),
                "text_targets": 0,
                "exact_terms_present": [],
                "source_label_terms_present": [],
                "missing_terms": [],
                "exact_term_coverage": 0.0,
                "source_label_coverage": 0.0,
            }

        exact_present: set[str] = set()
        source_label_present: set[str] = set()
        text_targets = 0
        for match in matches:
            text = ""
            source_label = ""
            if match.get("kind") == "message":
                row = conn.execute(
                    """
                    SELECT COALESCE(m.text, '') AS text, COALESCE(c.name, m.channel_id, '') AS source_label
                    FROM messages m
                    LEFT JOIN channels c
                      ON c.workspace_id = m.workspace_id
                     AND c.channel_id = m.channel_id
                    WHERE m.workspace_id = ?
                      AND m.channel_id = ?
                      AND m.ts = ?
                    LIMIT 1
                    """,
                    (workspace_id, match.get("channel_id"), match.get("ts")),
                ).fetchone()
                if row:
                    text = str(row["text"] or "")
                    source_label = str(row["source_label"] or "")
            elif match.get("kind") == "derived_text":
                row = conn.execute(
                    """
                    SELECT COALESCE(dt.text, '') AS text,
                           COALESCE(f.title, f.name, c.title, dt.source_id, '') AS source_label
                    FROM derived_text dt
                    LEFT JOIN files f
                      ON dt.source_kind = 'file'
                     AND f.workspace_id = dt.workspace_id
                     AND f.file_id = dt.source_id
                    LEFT JOIN canvases c
                      ON dt.source_kind = 'canvas'
                     AND c.workspace_id = dt.workspace_id
                     AND c.canvas_id = dt.source_id
                    WHERE dt.workspace_id = ?
                      AND dt.id = ?
                    LIMIT 1
                    """,
                    (workspace_id, match.get("derived_text_id")),
                ).fetchone()
                if row:
                    text = str(row["text"] or "")
                    source_label = str(row["source_label"] or "")

            normalized_text = text.lower()
            normalized_source_label = source_label.lower()
            if normalized_text:
                text_targets += 1
            for term in query_terms:
                if term in normalized_text:
                    exact_present.add(term)
                if term in normalized_source_label:
                    source_label_present.add(term)

        covered_terms = exact_present | source_label_present
        return {
            "query_terms": query_terms,
            "resolved_targets": len(matches),
            "text_targets": text_targets,
            "exact_terms_present": sorted(exact_present),
            "source_label_terms_present": sorted(source_label_present),
            "missing_terms": [term for term in query_terms if term not in covered_terms],
            "exact_term_coverage": round(len(exact_present) / len(query_terms), 6),
            "source_label_coverage": round(len(source_label_present) / len(query_terms), 6),
        }

    def _benchmark_result_diagnostic(self, result: dict[str, Any], *, rank: int, include_text: bool = False) -> dict[str, Any]:
        labels: list[str] = []
        payload: dict[str, Any] = {
            "rank": int(rank),
            "kind": result.get("result_kind"),
            "labels": labels,
            "source_label": result.get("source_label"),
            "action_target": result.get("action_target"),
            "explain": _compact_explain(result.get("_explain") or {}),
        }
        if result.get("result_kind") == "message":
            labels.append(f"{result.get('channel_id')}:{result.get('ts')}")
            if result.get("channel_name"):
                labels.append(f"{result.get('channel_name')}:{result.get('ts')}")
            payload.update(
                {
                    "channel_id": result.get("channel_id"),
                    "channel_name": result.get("channel_name"),
                    "ts": result.get("ts"),
                    "thread_ts": result.get("thread_ts"),
                    "user_id": result.get("user_id"),
                }
            )
        elif result.get("result_kind") == "derived_text":
            labels.append(
                f"{result.get('source_kind')}:{result.get('source_id')}:{result.get('derivation_kind')}:{result.get('extractor')}"
            )
            payload.update(
                {
                    "derived_text_id": result.get("id"),
                    "source_kind": result.get("source_kind"),
                    "source_id": result.get("source_id"),
                    "derivation_kind": result.get("derivation_kind"),
                    "extractor": result.get("extractor"),
                    "chunk_index": result.get("chunk_index"),
                }
            )
        if include_text:
            payload["text"] = result.get("text")
            payload["snippet_text"] = result.get("snippet_text")
        return payload

    def _benchmark_label_model_covered(self, conn, *, workspace_id: int, match: dict[str, Any], model_id: str) -> bool:
        if match["kind"] == "message":
            row = conn.execute(
                """
                SELECT 1
                FROM message_embeddings
                WHERE workspace_id = ?
                  AND channel_id = ?
                  AND ts = ?
                  AND model_id = ?
                LIMIT 1
                """,
                (workspace_id, match["channel_id"], match["ts"], model_id),
            ).fetchone()
            return row is not None
        if match["kind"] == "derived_text":
            row = conn.execute(
                """
                SELECT 1
                FROM derived_text_chunks dc
                JOIN derived_text_chunk_embeddings dte
                  ON dte.derived_text_chunk_id = dc.id
                 AND dte.workspace_id = dc.workspace_id
                WHERE dc.workspace_id = ?
                  AND dc.derived_text_id = ?
                  AND dte.model_id = ?
                LIMIT 1
                """,
                (workspace_id, match["derived_text_id"], model_id),
            ).fetchone()
            return row is not None
        return False

    def _search_scale_corpus_stats(self, conn, *, workspace_id: int) -> dict[str, Any]:
        message_count = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE workspace_id = ? AND deleted = 0",
                (workspace_id,),
            ).fetchone()["c"]
        )
        message_embedding_rows = conn.execute(
            """
            SELECT model_id, COUNT(*) AS c
            FROM message_embeddings
            WHERE workspace_id = ?
            GROUP BY model_id
            ORDER BY model_id
            """,
            (workspace_id,),
        ).fetchall()
        message_embeddings_by_model = {str(row["model_id"]): int(row["c"]) for row in message_embedding_rows}

        derived_rows = conn.execute(
            """
            SELECT derivation_kind, COUNT(*) AS c
            FROM derived_text
            WHERE workspace_id = ?
            GROUP BY derivation_kind
            ORDER BY derivation_kind
            """,
            (workspace_id,),
        ).fetchall()
        derived_counts = {str(row["derivation_kind"]): int(row["c"]) for row in derived_rows}
        chunk_rows = conn.execute(
            """
            SELECT dt.derivation_kind, COUNT(*) AS c
            FROM derived_text_chunks dc
            JOIN derived_text dt ON dt.id = dc.derived_text_id
            WHERE dt.workspace_id = ?
            GROUP BY dt.derivation_kind
            ORDER BY dt.derivation_kind
            """,
            (workspace_id,),
        ).fetchall()
        chunk_counts = {str(row["derivation_kind"]): int(row["c"]) for row in chunk_rows}
        chunk_embedding_rows = conn.execute(
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
        chunk_embeddings_by_model: dict[str, dict[str, int]] = {}
        for row in chunk_embedding_rows:
            kind = str(row["derivation_kind"])
            chunk_embeddings_by_model.setdefault(kind, {})[str(row["model_id"])] = int(row["c"])

        return {
            "messages": {
                "count": message_count,
                "embeddings_by_model": message_embeddings_by_model,
                "embedding_rows": sum(message_embeddings_by_model.values()),
            },
            "derived_text": {
                "counts": {
                    "attachment_text": int(derived_counts.get("attachment_text", 0)),
                    "ocr_text": int(derived_counts.get("ocr_text", 0)),
                    "total": sum(derived_counts.values()),
                },
                "chunk_counts": {
                    "attachment_text": int(chunk_counts.get("attachment_text", 0)),
                    "ocr_text": int(chunk_counts.get("ocr_text", 0)),
                    "total": sum(chunk_counts.values()),
                },
                "chunk_embeddings_by_model": chunk_embeddings_by_model,
                "chunk_embedding_rows": sum(sum(model_counts.values()) for model_counts in chunk_embeddings_by_model.values()),
            },
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
        fusion_method: str = "weighted",
        lexical_weight: float = 0.6,
        semantic_weight: float = 0.4,
        semantic_scale: float = 10.0,
        min_hit_at_3: float = 0.5,
        min_hit_at_10: float = 0.8,
        min_ndcg_at_k: float = 0.6,
        max_latency_p95_ms: float = 800.0,
        max_attachment_pending: int = 25,
        max_ocr_pending: int = 25,
        message_embedding_provider=None,
        rerank: bool = False,
        rerank_top_n: int = 50,
        reranker_provider=None,
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
            "fusion_method": fusion_method if benchmark_target == "corpus" else None,
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
            embedding_provider = message_embedding_provider or self.message_embedding_provider()
            if benchmark_target == "derived_text":
                benchmark = evaluate_derived_text_search(
                    conn,
                    workspace_id=workspace_id,
                    dataset=dataset,
                    mode=mode,
                    limit=limit,
                    model_id=model_id,
                    embedding_provider=embedding_provider,
                )
            else:
                benchmark = evaluate_corpus_search(
                    conn,
                    workspace_id=workspace_id,
                    dataset=dataset,
                    mode=mode,
                    limit=limit,
                    model_id=model_id,
                    fusion_method=fusion_method,
                    lexical_weight=lexical_weight,
                    semantic_weight=semantic_weight,
                    semantic_scale=semantic_scale,
                    embedding_provider=embedding_provider,
                    rerank=rerank,
                    rerank_top_n=rerank_top_n,
                    reranker_provider=reranker_provider,
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

    def _append_outbound_child_event(
        self,
        conn,
        *,
        workspace_id: int,
        workspace: str,
        action: dict[str, Any],
        auth_mode: str,
        status: str,
        response: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        action_id = int(action["id"])
        kind = str(action.get("kind") or "message")
        channel_id = str((response or {}).get("channel") or action.get("channel_id") or "")
        response_ts = str((response or {}).get("ts") or "").strip()
        event_type = (
            "slack.outbound.write.failed"
            if status == "failed"
            else "slack.outbound.thread_reply.sent"
            if kind == "thread_reply"
            else "slack.outbound.message.sent"
        )
        subject_kind = "slack-outbound-action" if status == "failed" or not response_ts else "slack-message"
        subject_id = (
            f"message|{workspace}|{channel_id}|{response_ts}"
            if subject_kind == "slack-message"
            else f"outbound|{workspace}|{action_id}"
        )
        source_refs = {
            "workspace": workspace,
            "action_id": action_id,
            "kind": kind,
            "channel_id": channel_id or None,
            "thread_ts": action.get("thread_ts"),
            "idempotency_key": action.get("idempotency_key"),
            "auth_mode": auth_mode,
            "ts": response_ts or None,
        }
        payload = {
            "actionId": action_id,
            "kind": kind,
            "status": status,
            "authMode": auth_mode,
            "textPreview": _truncate_text(action.get("text"), 160),
            "idempotencyKey": action.get("idempotency_key"),
            "threadTs": action.get("thread_ts"),
            "responseOk": bool((response or {}).get("ok")) if response is not None else None,
            "error": _truncate_text(error, 240) if error else None,
        }
        db.append_child_event(
            conn,
            workspace_id=workspace_id,
            event_id=f"{event_type}|{action_id}|{status}",
            event_type=event_type,
            subject_kind=subject_kind,
            subject_id=subject_id,
            channel_id=channel_id or None,
            source_refs={key: value for key, value in source_refs.items() if value is not None},
            payload={key: value for key, value in payload.items() if value is not None},
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
            self._append_outbound_child_event(
                conn,
                workspace_id=workspace_id,
                workspace=workspace,
                action=action,
                auth_mode=auth_mode,
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
            self._append_outbound_child_event(
                conn,
                workspace_id=workspace_id,
                workspace=workspace,
                action=action,
                auth_mode=auth_mode,
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
            self._append_outbound_child_event(
                conn,
                workspace_id=workspace_id,
                workspace=workspace,
                action=action,
                auth_mode=auth_mode,
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
            self._append_outbound_child_event(
                conn,
                workspace_id=workspace_id,
                workspace=workspace,
                action=action,
                auth_mode=auth_mode,
                status="failed",
                error=str(exc),
            )
            raise


def _coverage_payload(total: int, ready: int) -> dict[str, Any]:
    missing = max(int(total) - int(ready), 0)
    ratio = 1.0 if int(total) <= 0 else int(ready) / max(int(total), 1)
    return {
        "total": int(total),
        "ready": int(ready),
        "missing": missing,
        "coverage_ratio": round(ratio, 6),
        "complete": missing == 0,
    }


def _latency_summary(latencies_ms: list[float]) -> dict[str, float]:
    if not latencies_ms:
        return {"min": 0.0, "max": 0.0, "avg": 0.0, "p95": 0.0}
    ordered = sorted(float(value) for value in latencies_ms)
    p95_index = min(len(ordered) - 1, max(0, int((len(ordered) * 0.95) + 0.999999) - 1))
    return {
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
        "avg": round(sum(ordered) / len(ordered), 3),
        "p95": round(ordered[p95_index], 3),
    }


def _search_scale_decision(corpus: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    message_count = int(dict(corpus.get("messages") or {}).get("count") or 0)
    chunk_counts = dict(dict(corpus.get("derived_text") or {}).get("chunk_counts") or {})
    chunk_count = int(chunk_counts.get("total") or 0)
    p95_values = [float(dict(run.get("latency_ms") or {}).get("p95") or 0.0) for run in runs]
    max_p95 = max(p95_values) if p95_values else 0.0
    total_vector_rows = message_count + chunk_count

    index_backend = "sqlite_exact"
    index_reason = "Current corpus size and measured latency do not justify a vector-index migration."
    if total_vector_rows >= 250_000 or max_p95 >= 1500.0:
        index_backend = "evaluate_sqlite_vector_extension"
        index_reason = "Corpus size or measured p95 latency is high enough to evaluate a SQLite-native vector extension before any vector DB."
    if total_vector_rows >= 1_000_000 or max_p95 >= 5000.0:
        index_backend = "evaluate_ann_service"
        index_reason = "Corpus size or measured p95 latency is high enough to evaluate a local ANN service after SQLite-native options."

    uses_heavy_profile = any(
        str(dict(run).get("model") or "").lower() not in {"", "local-hash-128"} or bool(dict(run).get("rerank"))
        for run in runs
    )
    inference_boundary = "in_process_for_baseline"
    inference_reason = "The baseline profile is lightweight enough to remain in process."
    if uses_heavy_profile:
        inference_boundary = "long_lived_local_inference_service_recommended"
        inference_reason = "Heavy embedding or reranker profiles should not be independently loaded by every CLI/API/MCP client."

    return {
        "index_backend": index_backend,
        "index_reason": index_reason,
        "inference_boundary": inference_boundary,
        "inference_reason": inference_reason,
        "max_p95_ms": round(max_p95, 3),
        "vector_rows_considered": total_vector_rows,
        "summary": f"{index_backend}; {inference_boundary}.",
    }


def _semantic_profile_state(
    *,
    plan: dict[str, Any],
    provider_probe: dict[str, Any],
    reranker_probe: dict[str, Any] | None,
) -> dict[str, str]:
    if not bool(provider_probe.get("available")):
        issues = ", ".join(str(item) for item in provider_probe.get("issues") or []) or "provider unavailable"
        return {
            "state": "provider_unavailable",
            "tone": "bad",
            "summary": f"Embedding provider is unavailable: {issues}.",
        }
    if reranker_probe is not None and not bool(reranker_probe.get("available")):
        issues = ", ".join(str(item) for item in reranker_probe.get("issues") or []) or "reranker unavailable"
        return {
            "state": "reranker_unavailable",
            "tone": "bad",
            "summary": f"Reranker provider is unavailable: {issues}.",
        }
    coverage = dict(plan.get("coverage") or {})
    messages = dict(coverage.get("messages") or {})
    chunks = dict(coverage.get("derived_text_chunks") or {})
    missing_messages = int(messages.get("missing") or 0)
    missing_chunks = int(chunks.get("missing") or 0)
    ready_messages = int(messages.get("ready") or 0)
    ready_chunks = int(chunks.get("ready") or 0)
    if missing_messages == 0 and missing_chunks == 0:
        return {
            "state": "ready",
            "tone": "ok",
            "summary": "Profile coverage is complete for messages and current derived-text chunks.",
        }
    if ready_messages > 0 or ready_chunks > 0:
        return {
            "state": "partial_rollout",
            "tone": "warn",
            "summary": f"Profile rollout is partial: {missing_messages} messages and {missing_chunks} derived-text chunks still need embeddings.",
        }
    return {
        "state": "rollout_needed",
        "tone": "warn",
        "summary": f"Profile rollout has not started: {missing_messages} messages and {missing_chunks} derived-text chunks need embeddings.",
    }


def _semantic_workspace_state(profiles: list[dict[str, Any]]) -> dict[str, str]:
    if not profiles:
        return {"state": "unknown", "tone": "neutral", "summary": "No retrieval profiles are configured."}
    ready = [profile for profile in profiles if profile.get("state") == "ready"]
    if ready:
        names = ", ".join(str(profile.get("name")) for profile in ready)
        return {"state": "ready", "tone": "ok", "summary": f"Ready profiles: {names}."}
    bad = [profile for profile in profiles if str(profile.get("state") or "").endswith("_unavailable")]
    if len(bad) == len(profiles):
        return {"state": "unavailable", "tone": "bad", "summary": "All semantic profiles have unavailable providers."}
    partial = [profile for profile in profiles if profile.get("state") == "partial_rollout"]
    if partial:
        names = ", ".join(str(profile.get("name")) for profile in partial)
        return {"state": "partial_rollout", "tone": "warn", "summary": f"Partial rollout profiles: {names}."}
    return {"state": "rollout_needed", "tone": "warn", "summary": "No stronger semantic profile is ready yet."}


def get_app_service(config_path: str | None = None) -> SlackMirrorAppService:
    return SlackMirrorAppService(config_path=config_path)
