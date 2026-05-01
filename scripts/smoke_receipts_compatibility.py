#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import requests

from slack_mirror.core.db import upsert_channel, upsert_message, upsert_user
from slack_mirror.service.api import create_api_server
from slack_mirror.service.app import get_app_service


class SmokeFailure(RuntimeError):
    def __init__(self, surface: str, message: str):
        super().__init__(message)
        self.surface = surface


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke Slack Mirror's Receipts-facing child-service contract.")
    parser.add_argument("--base-url", help="Run against an existing Slack Mirror API instead of a seeded fixture server.")
    parser.add_argument("--username", default=os.environ.get("SLACK_MIRROR_FRONTEND_USERNAME") or os.environ.get("RECEIPTS_SLACK_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("SLACK_MIRROR_FRONTEND_PASSWORD") or os.environ.get("RECEIPTS_SLACK_PASSWORD"))
    parser.add_argument("--query", default="incident", help="Live-mode search query used to discover a message result when --result-id is omitted.")
    parser.add_argument("--search-mode", default="lexical", choices=("lexical", "hybrid", "semantic"), help="Live-mode search mode used only for target discovery.")
    parser.add_argument("--result-id", help="Live-mode Slack message result id, for example message|default|C123|1712870400.000100.")
    parser.add_argument("--json", action="store_true", help="Emit a structured JSON result.")
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    server_context = None
    try:
        if args.base_url:
            base_url = args.base_url.rstrip("/")
            session = requests.Session()
            if not args.username or not args.password:
                raise SmokeFailure("auth", "--base-url mode requires --username/--password or Slack frontend auth env vars")
            login(session, base_url, args.username, args.password, checks)
            result_id = args.result_id
            target = None
        else:
            server_context = start_fixture_server()
            base_url = server_context["base_url"]
            session = requests.Session()
            register_fixture_user(session, base_url, checks)
            result_id = "message|default|C123|11.0"
            target = {"kind": "message", "workspace": "default", "channel_id": "C123", "ts": "11.0"}

        run_contract_smoke(session=session, base_url=base_url, checks=checks, result_id=result_id, target=target, query=args.query, search_mode=args.search_mode)
    except Exception as exc:  # noqa: BLE001 - convert all smoke failures into structured output.
        surface = exc.surface if isinstance(exc, SmokeFailure) else "unexpected"
        checks.append({"name": surface, "ok": False, "error": str(exc)})
        emit({"ok": False, "base_url": args.base_url or (server_context or {}).get("base_url"), "checks": checks}, as_json=args.json)
        return 1
    finally:
        if server_context is not None:
            stop_fixture_server(server_context)

    emit({"ok": True, "base_url": base_url, "checks": checks}, as_json=args.json)
    return 0


def emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    status = "PASS" if payload.get("ok") else "FAIL"
    print(f"{status} receipts_compatibility")
    print(f"base_url={payload.get('base_url')}")
    for check in payload.get("checks", []):
        line = f"{'PASS' if check.get('ok') else 'FAIL'} {check.get('name')}"
        if check.get("detail"):
            line += f" {check['detail']}"
        if check.get("error"):
            line += f" error={check['error']}"
        print(line)


def start_fixture_server() -> dict[str, Any]:
    tempdir = tempfile.TemporaryDirectory(prefix="slack-mirror-receipts-compat-")
    root = Path(tempdir.name)
    config_path = root / "config.yaml"
    db_path = root / "data" / "mirror.db"
    export_root = root / "exports"
    config_path.write_text(
        "\n".join(
            [
                "version: 1",
                f"dotenv: {root / 'tenant.env'}",
                "storage:",
                f"  db_path: {db_path}",
                "workspaces:",
                "  - name: default",
                "    team_id: T123",
                "    token: xoxb-test-token",
                "    user_token: xoxp-test-token",
                "exports:",
                f"  root_dir: {export_root}",
                "  local_base_url: http://slack.localhost",
                "  external_base_url: https://slack.example.test",
                "service:",
                "  auth:",
                "    enabled: true",
                "    allow_registration: true",
                "    cookie_secure_mode: never",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "tenant.env").write_text("", encoding="utf-8")

    service = get_app_service(str(config_path))
    conn = service.connect()
    workspace_id = service.workspace_id(conn, "default")
    upsert_channel(conn, workspace_id, {"id": "C123", "name": "general", "is_private": False})
    upsert_user(conn, workspace_id, {"id": "U1", "name": "eric", "real_name": "Eric Example", "profile": {"display_name": "Eric"}})
    upsert_user(conn, workspace_id, {"id": "U2", "name": "alex", "real_name": "Alex Analyst"})
    upsert_message(
        conn,
        workspace_id,
        "C123",
        {"ts": "10.0", "user": "U1", "text": "before context", "channel": "C123"},
    )
    upsert_message(
        conn,
        workspace_id,
        "C123",
        {"ts": "11.0", "user": "U1", "text": "fixture incident for <@U2> :rocket:", "channel": "C123"},
    )
    upsert_message(
        conn,
        workspace_id,
        "C123",
        {"ts": "12.0", "user": "U2", "text": "after context", "channel": "C123"},
    )

    server = create_api_server(bind="127.0.0.1", port=0, config_path=str(config_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return {
        "tempdir": tempdir,
        "server": server,
        "thread": thread,
        "base_url": f"http://127.0.0.1:{server.server_address[1]}",
    }


def stop_fixture_server(context: dict[str, Any]) -> None:
    server = context["server"]
    server.shutdown()
    server.server_close()
    context["thread"].join(timeout=2)
    context["tempdir"].cleanup()


def register_fixture_user(session: requests.Session, base_url: str, checks: list[dict[str, Any]]) -> None:
    response = session.post(
        f"{base_url}/auth/register",
        json={"username": "receipts-smoke", "display_name": "Receipts Smoke", "password": "correct-horse-123"},
        headers={"Origin": base_url},
        timeout=10,
    )
    expect_json(response, 201, "auth")
    checks.append({"name": "auth", "ok": True, "detail": "fixture-user-registered"})


def login(session: requests.Session, base_url: str, username: str, password: str, checks: list[dict[str, Any]]) -> None:
    response = session.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": base_url},
        timeout=10,
    )
    payload = expect_json(response, 200, "auth")
    if payload.get("session", {}).get("authenticated") is not True:
        raise SmokeFailure("auth", "login did not return an authenticated session")
    checks.append({"name": "auth", "ok": True, "detail": "logged-in"})


def run_contract_smoke(
    *,
    session: requests.Session,
    base_url: str,
    checks: list[dict[str, Any]],
    result_id: str | None,
    target: dict[str, Any] | None,
    query: str,
    search_mode: str,
) -> None:
    profile = expect_json(requests.get(f"{base_url}/v1/service-profile", timeout=10), 200, "profile")["profile"]
    require(profile.get("capabilities", {}).get("guestGrants") is True, "profile", "guestGrants capability missing")
    require(profile.get("capabilities", {}).get("eventCursorRead") is True, "profile", "eventCursorRead capability missing")
    require(profile.get("guestGrants", {}).get("assertionsUnderstood") is True, "profile", "guestGrants assertion policy missing")
    checks.append({"name": "profile", "ok": True, "detail": "service-profile"})

    if target is None or result_id is None:
        target = discover_message_target(session=session, base_url=base_url, query=query, search_mode=search_mode, result_id=result_id)
        result_id = str(target.get("id") or "")
        checks.append({"name": "target-discovery", "ok": True, "detail": result_id})

    context = expect_json(
        session.get(
            f"{base_url}/v1/context-window",
            params={"result_id": result_id, "direction": "around", "limit": "3"},
            timeout=10,
        ),
        200,
        "context",
    )["contextWindow"]
    require(context.get("selectedItemId") == result_id, "context", "selected item did not round-trip")
    require(context.get("items"), "context", "context window returned no items")
    checks.append({"name": "context", "ok": True, "detail": f"items={len(context.get('items', []))}"})

    export_id = f"receipts-compat-smoke-{int(time.time())}"
    created = expect_json(
        session.post(
            f"{base_url}/v1/exports",
            json={
                "kind": "selected-results",
                "targets": [target],
                "before": 1,
                "after": 1,
                "include_text": True,
                "max_text_chars": 500,
                "audience": "local",
                "export_id": export_id,
                "title": "Receipts compatibility smoke",
            },
            headers={"Origin": base_url},
            timeout=10,
        ),
        201,
        "artifact",
    )["export"]
    require(created.get("export_id") == export_id, "artifact", "created export id mismatch")
    checks.append({"name": "artifact-create", "ok": True, "detail": export_id})

    tenant = str(target.get("workspace") or "default")
    events = expect_json(session.get(f"{base_url}/v1/events", params={"tenant": tenant, "limit": "5"}, timeout=10), 200, "events")
    require(isinstance(events.get("events"), list), "events", "events payload missing events list")
    status = expect_json(session.get(f"{base_url}/v1/events/status", params={"tenant": tenant}, timeout=10), 200, "events")
    require(status.get("descriptors"), "events", "event status missing descriptors")
    checks.append({"name": "events", "ok": True, "detail": f"count={events.get('count')}"})

    html = session.get(f"{base_url}/exports/{export_id}", timeout=10)
    require(html.status_code == 200 and "Receipts compatibility smoke" in html.text, "artifact", "authenticated artifact open failed")
    checks.append({"name": "artifact-open", "ok": True, "detail": "authenticated"})

    guest_headers = receipts_guest_headers()
    guest_html = requests.get(f"{base_url}/exports/{export_id}", headers=guest_headers, timeout=10)
    require(guest_html.status_code == 200 and "Receipts compatibility smoke" in guest_html.text, "guest-grants", "guest artifact read failed")
    checks.append({"name": "guest-artifact-read", "ok": True, "detail": "allowed"})

    expect_error(
        requests.get(f"{base_url}/v1/search/corpus", params={"query": "fixture"}, headers=guest_headers, timeout=10),
        403,
        "RECEIPTS_GUEST_GRANT_REJECTED",
        "guest-grants",
    )
    expect_error(
        requests.get(f"{base_url}/v1/exports", headers=guest_headers, timeout=10),
        403,
        "RECEIPTS_GUEST_GRANT_REJECTED",
        "guest-grants",
    )
    expect_error(
        requests.post(f"{base_url}/v1/exports", json={}, headers={**guest_headers, "Origin": base_url}, timeout=10),
        403,
        "RECEIPTS_GUEST_GRANT_REJECTED",
        "guest-grants",
    )
    checks.append({"name": "guest-local-only-denials", "ok": True, "detail": "search,list,mutation"})

    session.delete(f"{base_url}/v1/exports/{export_id}", headers={"Origin": base_url}, timeout=10)


def discover_message_target(
    *,
    session: requests.Session,
    base_url: str,
    query: str,
    search_mode: str,
    result_id: str | None,
) -> dict[str, Any]:
    if result_id:
        parsed = parse_message_result_id(result_id)
        if parsed is not None:
            return parsed
        raise SmokeFailure("target-discovery", f"--result-id must identify a Slack message: {result_id}")
    payload = expect_json(
        session.get(f"{base_url}/v1/search/corpus", params={"query": query, "mode": search_mode, "limit": "10"}, timeout=30),
        200,
        "target-discovery",
    )
    for row in payload.get("results") or []:
        if not isinstance(row, dict):
            continue
        target = row.get("action_target")
        if isinstance(target, dict) and target.get("kind") == "message" and target.get("id"):
            return target
    raise SmokeFailure("target-discovery", f"no message action_target found for live query {query!r} in {search_mode} mode; pass --result-id")


def parse_message_result_id(result_id: str) -> dict[str, Any] | None:
    parts = result_id.split("|")
    if len(parts) != 4 or parts[0] != "message":
        return None
    return {
        "version": 1,
        "kind": "message",
        "id": result_id,
        "workspace": parts[1],
        "channel_id": parts[2],
        "ts": parts[3],
        "selection_label": f"{parts[1]}:{parts[2]}:{parts[3]}",
    }


def receipts_guest_headers() -> dict[str, str]:
    return {
        "x-receipts-request-mode": "guest-grant",
        "x-receipts-child-service": "slack",
        "x-receipts-guest-grant-id": "grant-smoke",
        "x-receipts-guest-grant-target-id": "target-smoke",
        "x-receipts-guest-grant-target-kind": "report-artifact",
        "x-receipts-guest-grant-token-id": "token-smoke",
        "x-receipts-guest-grant-scope": "report-bundle",
        "x-receipts-guest-grant-audience": "guest-link",
        "x-receipts-guest-grant-permissions": "view",
        "x-receipts-guest-grant-ts": "2026-05-01T12:00:00Z",
        "x-receipts-guest-grant-nonce": "00000000-0000-4000-8000-000000000001",
        "x-receipts-guest-grant-signature-mode": "unsigned",
    }


def expect_json(response: requests.Response, status: int, surface: str) -> dict[str, Any]:
    if response.status_code != status:
        raise SmokeFailure(surface, f"expected HTTP {status}, got {response.status_code}: {response.text[:500]}")
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise SmokeFailure(surface, f"unexpected JSON payload: {payload!r}")
    return payload


def expect_error(response: requests.Response, status: int, code: str, surface: str) -> None:
    if response.status_code != status:
        raise SmokeFailure(surface, f"expected HTTP {status}, got {response.status_code}: {response.text[:500]}")
    payload = response.json()
    if payload.get("error", {}).get("code") != code:
        raise SmokeFailure(surface, f"expected error {code}, got {payload!r}")


def require(condition: Any, surface: str, message: str) -> None:
    if not condition:
        raise SmokeFailure(surface, message)


if __name__ == "__main__":
    raise SystemExit(main())
