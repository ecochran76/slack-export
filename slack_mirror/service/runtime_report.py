from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import requests

from slack_mirror.core.config import load_config


RUNTIME_REPORT_RETENTION_MAX_SNAPSHOTS = 24
RUNTIME_REPORT_RETENTION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
_SNAPSHOT_STEM_RE = re.compile(r"^(?P<name>.+)-(?P<stamp>\d{8}T\d{6}Z)$")
_REPORT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _db_path_from_config(config_path: str | None) -> Path:
    cfg = load_config(config_path)
    db_path = cfg.get("storage", {}).get("db_path", "./data/slack_mirror.db")
    return Path(str(db_path)).expanduser()


def runtime_report_dir_for_config(config_path: str | None) -> Path:
    db_path = _db_path_from_config(config_path)
    return db_path.parent / "runtime-reports"


def _safe_runtime_report_name(name: str) -> str:
    value = str(name or "").strip()
    if not value or not _REPORT_NAME_RE.fullmatch(value):
        raise ValueError(f"Invalid runtime report name: {name}")
    return value


def list_runtime_report_manifests(config_path: str | None) -> list[dict[str, Any]]:
    report_dir = runtime_report_dir_for_config(config_path)
    if not report_dir.exists():
        return []
    manifests: list[dict[str, Any]] = []
    for path in sorted(report_dir.glob("*.latest.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = str(payload.get("name") or "").strip()
        if not name:
            continue
        manifests.append(payload)
    manifests.sort(key=lambda item: str(item.get("fetched_at") or ""), reverse=True)
    return manifests


def get_runtime_report_manifest(config_path: str | None, name: str) -> dict[str, Any] | None:
    safe_name = _safe_runtime_report_name(name)
    report_dir = runtime_report_dir_for_config(config_path)
    path = report_dir / f"{safe_name}.latest.json"
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if str(payload.get("name") or "") != safe_name:
        return None
    return payload


def _parse_snapshot_timestamp(path: Path, *, expected_name: str) -> datetime | None:
    if path.suffix not in {".md", ".html"}:
        return None
    match = _SNAPSHOT_STEM_RE.match(path.stem)
    if not match or match.group("name") != expected_name:
        return None
    try:
        return datetime.strptime(match.group("stamp"), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _prune_runtime_report_snapshots(
    *,
    report_dir: Path,
    name: str,
    now: datetime,
    keep_count: int = RUNTIME_REPORT_RETENTION_MAX_SNAPSHOTS,
    max_age_seconds: int = RUNTIME_REPORT_RETENTION_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for path in report_dir.iterdir():
        stamp_dt = _parse_snapshot_timestamp(path, expected_name=name)
        if stamp_dt is None:
            continue
        record = grouped.setdefault(
            path.stem,
            {
                "stamp_dt": stamp_dt,
                "paths": [],
            },
        )
        record["paths"].append(path)

    ordered = sorted(grouped.values(), key=lambda item: item["stamp_dt"], reverse=True)
    pruned_paths: list[str] = []
    kept = 0
    for item in ordered:
        age_seconds = (now - item["stamp_dt"]).total_seconds()
        should_keep = kept < keep_count and age_seconds <= max_age_seconds
        if should_keep:
            kept += 1
            continue
        for path in item["paths"]:
            path.unlink(missing_ok=True)
            pruned_paths.append(str(path))
    return {
        "kept_snapshot_sets": kept,
        "pruned_snapshot_sets": max(0, len(ordered) - kept),
        "pruned_paths": sorted(pruned_paths),
        "retention_max_snapshots": keep_count,
        "retention_max_age_seconds": max_age_seconds,
    }


def _fetch_json(url: str, *, timeout: float) -> dict[str, Any]:
    response = requests.get(url, timeout=timeout)
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"non-JSON response from {url}: {exc}") from exc
    if response.status_code not in {200, 503}:
        raise RuntimeError(f"unexpected status {response.status_code} from {url}")
    return payload


def _badge_class(ok: bool, status: str) -> str:
    if not ok or status == "fail":
        return "fail"
    if status == "pass_with_warnings":
        return "warn"
    return "ok"


def render_runtime_report_markdown(
    *,
    base_url: str,
    fetched_at: str,
    runtime_status: dict[str, Any],
    live_validation: dict[str, Any],
) -> str:
    status_payload = runtime_status.get("status", {})
    validation_payload = live_validation.get("validation", {})
    lines: list[str] = [
        "# Slack Mirror Runtime Report",
        "",
        f"- Base URL: `{base_url}`",
        f"- Fetched at: `{fetched_at}`",
        "",
        "## Summary",
        "",
        f"- Runtime status ok: `{runtime_status.get('ok', False)}`",
        f"- Live validation status: `{validation_payload.get('status', 'unknown')}`",
        f"- Live validation summary: `{validation_payload.get('summary', 'unknown')}`",
        "",
        "## Managed Runtime",
        "",
        f"- Wrappers present: `{status_payload.get('wrappers_present', False)}`",
        f"- API service present: `{status_payload.get('api_service_present', False)}`",
        f"- Config present: `{status_payload.get('config_present', False)}`",
        f"- DB present: `{status_payload.get('db_present', False)}`",
        f"- Cache present: `{status_payload.get('cache_present', False)}`",
        f"- Rollback snapshot present: `{status_payload.get('rollback_snapshot_present', False)}`",
        "",
        "## Services",
        "",
    ]
    for name, state in sorted((status_payload.get("services") or {}).items()):
        lines.append(f"- `{name}`: `{state}`")
    lines.extend(["", "## Reconcile State", ""])
    for workspace in status_payload.get("reconcile_workspaces") or []:
        if not workspace.get("state_present"):
            lines.append(f"- `{workspace['name']}`: no persisted reconcile state")
            continue
        age_seconds = workspace.get("age_seconds")
        age_fragment = f", age={int(age_seconds)}s" if age_seconds is not None else ""
        lines.append(
            f"- `{workspace['name']}`: downloaded=`{workspace.get('downloaded', 0)}` "
            f"warnings=`{workspace.get('warnings', 0)}` failed=`{workspace.get('failed', 0)}`{age_fragment}"
        )
    lines.extend(["", "## Live Validation", ""])
    if validation_payload.get("failure_codes"):
        lines.append("- Failures:")
        for code in validation_payload["failure_codes"]:
            lines.append(f"  - `{code}`")
    if validation_payload.get("warning_codes"):
        lines.append("- Warnings:")
        for code in validation_payload["warning_codes"]:
            lines.append(f"  - `{code}`")
    lines.extend(["", "## Workspaces", ""])
    for workspace in validation_payload.get("workspaces") or []:
        lines.append(f"### `{workspace['name']}`")
        lines.append(f"- Event pending: `{workspace.get('event_pending', 0)}`")
        lines.append(f"- Embedding pending: `{workspace.get('embedding_pending', 0)}`")
        lines.append(f"- Stale channels: `{workspace.get('stale_channels', 0)}`")
        lines.append(f"- Reconcile state present: `{workspace.get('reconcile_state_present', False)}`")
        if workspace.get("reconcile_state_present"):
            lines.append(f"- Reconcile downloaded: `{workspace.get('reconcile_downloaded', 0)}`")
            lines.append(f"- Reconcile warnings: `{workspace.get('reconcile_warnings', 0)}`")
            lines.append(f"- Reconcile failed: `{workspace.get('reconcile_failed', 0)}`")
        if workspace.get("warning_codes"):
            lines.append("- Workspace warnings:")
            for code in workspace["warning_codes"]:
                lines.append(f"  - `{code}`")
        if workspace.get("failure_codes"):
            lines.append("- Workspace failures:")
            for code in workspace["failure_codes"]:
                lines.append(f"  - `{code}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_runtime_report_html(
    *,
    base_url: str,
    fetched_at: str,
    runtime_status: dict[str, Any],
    live_validation: dict[str, Any],
) -> str:
    status_payload = runtime_status.get("status", {})
    validation_payload = live_validation.get("validation", {})
    validation_status = str(validation_payload.get("status", "unknown"))
    badge_class = _badge_class(bool(live_validation.get("ok", False)), validation_status)

    def code(text: Any) -> str:
        return f"<code>{escape(str(text))}</code>"

    service_rows = "".join(
        f"<tr><td>{code(name)}</td><td>{code(state)}</td></tr>"
        for name, state in sorted((status_payload.get("services") or {}).items())
    )

    def reconcile_age_label(item: dict[str, Any]) -> str:
        if not item.get("state_present"):
            return "missing"
        age_seconds = item.get("age_seconds")
        if age_seconds is None:
            return "unknown"
        return f"{int(age_seconds)}s"

    reconcile_rows = "".join(
        (
            f"<tr><td>{code(item['name'])}</td><td>{code(item.get('downloaded', 0))}</td>"
            f"<td>{code(item.get('warnings', 0))}</td><td>{code(item.get('failed', 0))}</td>"
            f"<td>{code(reconcile_age_label(item))}</td></tr>"
        )
        for item in (status_payload.get("reconcile_workspaces") or [])
    )
    workspace_cards = []
    for workspace in validation_payload.get("workspaces") or []:
        warning_items = "".join(f"<li>{code(item)}</li>" for item in workspace.get("warning_codes") or [])
        failure_items = "".join(f"<li>{code(item)}</li>" for item in workspace.get("failure_codes") or [])
        workspace_cards.append(
            "<section class='card workspace'>"
            f"<h3>{code(workspace['name'])}</h3>"
            f"<p>event_pending={code(workspace.get('event_pending', 0))} "
            f"embedding_pending={code(workspace.get('embedding_pending', 0))} "
            f"stale_channels={code(workspace.get('stale_channels', 0))}</p>"
            f"<p>reconcile_present={code(workspace.get('reconcile_state_present', False))} "
            f"downloaded={code(workspace.get('reconcile_downloaded', 0))} "
            f"warnings={code(workspace.get('reconcile_warnings', 0))} "
            f"failed={code(workspace.get('reconcile_failed', 0))}</p>"
            f"{('<div><strong>Warnings</strong><ul>' + warning_items + '</ul></div>') if warning_items else ''}"
            f"{('<div><strong>Failures</strong><ul>' + failure_items + '</ul></div>') if failure_items else ''}"
            "</section>"
        )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Slack Mirror Runtime Report</title>"
        "<style>"
        "body{font-family:Arial,sans-serif;margin:24px;background:#f8fafc;color:#0f172a}"
        "h1,h2,h3{margin:0 0 12px}"
        ".card{background:#fff;border:1px solid #dbe2ea;border-radius:12px;padding:16px;margin:0 0 16px}"
        ".badge{display:inline-block;padding:4px 10px;border-radius:999px;font-weight:700;font-size:12px}"
        ".badge.ok{background:#dcfce7;color:#166534}.badge.warn{background:#fef3c7;color:#92400e}.badge.fail{background:#fee2e2;color:#991b1b}"
        "table{width:100%;border-collapse:collapse}th,td{padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:left}"
        "code{background:#e2e8f0;padding:1px 5px;border-radius:6px}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}"
        "</style></head><body>"
        "<section class='card'>"
        "<h1>Slack Mirror Runtime Report</h1>"
        f"<p>Base URL: {code(base_url)}<br>Fetched at: {code(fetched_at)}</p>"
        f"<p><span class='badge {badge_class}'>{escape(validation_status)}</span> {escape(str(validation_payload.get('summary', 'Summary: UNKNOWN')))}</p>"
        "</section>"
        "<section class='grid'>"
        "<section class='card'><h2>Managed Runtime</h2>"
        f"<p>wrappers_present={code(status_payload.get('wrappers_present', False))}<br>"
        f"api_service_present={code(status_payload.get('api_service_present', False))}<br>"
        f"config_present={code(status_payload.get('config_present', False))}<br>"
        f"db_present={code(status_payload.get('db_present', False))}<br>"
        f"cache_present={code(status_payload.get('cache_present', False))}<br>"
        f"rollback_snapshot_present={code(status_payload.get('rollback_snapshot_present', False))}</p>"
        "</section>"
        "<section class='card'><h2>Validation</h2>"
        f"<p>failure_count={code(validation_payload.get('failure_count', 0))}<br>"
        f"warning_count={code(validation_payload.get('warning_count', 0))}</p>"
        "</section>"
        "</section>"
        "<section class='card'><h2>Services</h2><table><thead><tr><th>Service</th><th>State</th></tr></thead><tbody>"
        f"{service_rows}</tbody></table></section>"
        "<section class='card'><h2>Reconcile State</h2><table><thead><tr><th>Workspace</th><th>Downloaded</th><th>Warnings</th><th>Failed</th><th>Age</th></tr></thead><tbody>"
        f"{reconcile_rows}</tbody></table></section>"
        "<section class='card'><h2>Workspace Detail</h2>"
        f"{''.join(workspace_cards)}"
        "</section>"
        "</body></html>"
    )


def build_report_payload(*, base_url: str, timeout: float) -> dict[str, Any]:
    runtime_status = _fetch_json(f"{base_url.rstrip('/')}/v1/runtime/status", timeout=timeout)
    live_validation = _fetch_json(f"{base_url.rstrip('/')}/v1/runtime/live-validation", timeout=timeout)
    fetched_at = datetime.now(timezone.utc).isoformat()
    return {
        "base_url": base_url,
        "fetched_at": fetched_at,
        "runtime_status": runtime_status,
        "live_validation": live_validation,
    }


def build_report(*, base_url: str, output_format: str, timeout: float) -> str:
    payload = build_report_payload(base_url=base_url, timeout=timeout)
    if output_format == "html":
        return render_runtime_report_html(
            base_url=payload["base_url"],
            fetched_at=payload["fetched_at"],
            runtime_status=payload["runtime_status"],
            live_validation=payload["live_validation"],
        )
    return render_runtime_report_markdown(
        base_url=payload["base_url"],
        fetched_at=payload["fetched_at"],
        runtime_status=payload["runtime_status"],
        live_validation=payload["live_validation"],
    )


def write_runtime_report_snapshot(
    *,
    config_path: str | None,
    base_url: str,
    name: str,
    timeout: float,
) -> dict[str, Any]:
    safe_name = "-".join(part for part in name.strip().split() if part) or "runtime-report"
    safe_name = safe_name.replace("/", "-")
    payload = build_report_payload(base_url=base_url, timeout=timeout)
    markdown = render_runtime_report_markdown(**payload)
    html = render_runtime_report_html(**payload)
    report_dir = runtime_report_dir_for_config(config_path)
    report_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    stem = f"{safe_name}-{stamp}"
    markdown_path = report_dir / f"{stem}.md"
    html_path = report_dir / f"{stem}.html"
    latest_markdown_path = report_dir / f"{safe_name}.latest.md"
    latest_html_path = report_dir / f"{safe_name}.latest.html"
    latest_json_path = report_dir / f"{safe_name}.latest.json"
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    latest_markdown_path.write_text(markdown, encoding="utf-8")
    latest_html_path.write_text(html, encoding="utf-8")
    metadata = {
        "name": safe_name,
        "base_url": base_url,
        "fetched_at": payload["fetched_at"],
        "status": payload["live_validation"].get("validation", {}).get("status"),
        "summary": payload["live_validation"].get("validation", {}).get("summary"),
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
        "latest_markdown_path": str(latest_markdown_path),
        "latest_html_path": str(latest_html_path),
    }
    retention = _prune_runtime_report_snapshots(report_dir=report_dir, name=safe_name, now=now)
    metadata.update(retention)
    latest_json_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        **metadata,
        "latest_json_path": str(latest_json_path),
        "runtime_report_dir": str(report_dir),
    }
