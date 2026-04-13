from __future__ import annotations

import json
import mimetypes
import re
from http.cookies import SimpleCookie
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from slack_mirror.core.config import load_config
from slack_mirror.exports import build_export_manifest, list_export_manifests, resolve_export_base_urls, resolve_export_root, safe_export_path
from slack_mirror.service.frontend_auth import FrontendAuthConfig, FrontendAuthSession
from slack_mirror.service.runtime_report import runtime_report_dir_for_config, _safe_runtime_report_name
from slack_mirror.service.errors import map_service_error
from slack_mirror.service.app import get_app_service


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _error_response(handler: BaseHTTPRequestHandler, status: int, code: str, message: str) -> None:
    _json_response(handler, status, {"ok": False, "error": {"code": code, "message": message}})


def _service_error_response(handler: BaseHTTPRequestHandler, exc: Exception, **details: Any) -> None:
    error = map_service_error(exc, **details)
    _json_response(handler, error.http_status, {"ok": False, "error": error.envelope()})


def _file_response(handler: BaseHTTPRequestHandler, path: Path) -> None:
    data = path.read_bytes()
    content_type, _ = mimetypes.guess_type(str(path))
    handler.send_response(200)
    handler.send_header("content-type", content_type or "application/octet-stream")
    handler.send_header("content-length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _html_response(handler: BaseHTTPRequestHandler, status: int, body: str) -> None:
    data = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "text/html; charset=utf-8")
    handler.send_header("content-length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _redirect_response(handler: BaseHTTPRequestHandler, location: str, *, status: int = 303) -> None:
    handler.send_response(status)
    handler.send_header("location", location)
    handler.send_header("content-length", "0")
    handler.end_headers()


def _parse_cookie_value(handler: BaseHTTPRequestHandler, key: str) -> str | None:
    raw_cookie = handler.headers.get("Cookie", "")
    if not raw_cookie:
        return None
    cookie = SimpleCookie()
    cookie.load(raw_cookie)
    morsel = cookie.get(key)
    if morsel is None:
        return None
    return morsel.value


def _set_cookie_headers(
    handler: BaseHTTPRequestHandler,
    *,
    key: str,
    value: str,
    max_age: int | None,
    secure: bool,
) -> None:
    cookie = SimpleCookie()
    cookie[key] = value
    cookie[key]["path"] = "/"
    cookie[key]["httponly"] = True
    cookie[key]["samesite"] = "Lax"
    if secure:
        cookie[key]["secure"] = True
    if max_age is not None:
        cookie[key]["max-age"] = str(max_age)
    for morsel in cookie.values():
        handler.send_header("set-cookie", morsel.OutputString())


def _frontend_login_html(*, next_path: str, error: str | None = None, can_register: bool) -> str:
    error_html = ""
    if error:
        error_html = f"<p class='error'>{escape(error)}</p>"
    register_link = f"<p class='meta'>Need an account? <a href=\"/register?{urlencode({'next': next_path})}\">Register</a></p>" if can_register else ""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Slack Mirror Login</title>"
        "<style>"
        "body{font-family:Arial,sans-serif;background:#f8fafc;color:#0f172a;margin:0;padding:48px}"
        ".card{max-width:420px;margin:0 auto;background:#fff;border:1px solid #dbe2ea;border-radius:16px;padding:28px;box-shadow:0 10px 30px rgba(15,23,42,.08)}"
        "h1{margin:0 0 10px;font-size:28px}"
        "p{line-height:1.5}"
        "label{display:block;margin:14px 0 6px;font-weight:600}"
        "input{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px}"
        "button{margin-top:18px;width:100%;padding:11px 14px;border:none;border-radius:10px;background:#0b57d0;color:#fff;font-weight:700;font-size:14px;cursor:pointer}"
        ".error{color:#b91c1c;background:#fef2f2;border:1px solid #fecaca;padding:10px 12px;border-radius:10px}"
        ".meta{margin-top:14px;color:#475569;font-size:14px}"
        "code{background:#e2e8f0;padding:1px 5px;border-radius:6px}"
        "</style></head><body>"
        "<div class='card'>"
        "<h1>Slack Mirror</h1>"
        "<p>Sign in to access published exports and runtime reports.</p>"
        f"{error_html}"
        "<form id='login-form'>"
        "<label for='username'>Username</label>"
        "<input id='username' name='username' autocomplete='username' required />"
        "<label for='password'>Password</label>"
        "<input id='password' name='password' type='password' autocomplete='current-password' required />"
        "<button type='submit'>Sign in</button>"
        "</form>"
        f"{register_link}"
        f"<p class='meta'>After sign-in you will be redirected to <code>{escape(next_path)}</code>.</p>"
        "<script>"
        f"const nextPath={json.dumps(next_path)};"
        "document.getElementById('login-form').addEventListener('submit', async (event) => {"
        "event.preventDefault();"
        "const form=event.currentTarget;"
        "const payload={username:form.username.value,password:form.password.value};"
        "const resp=await fetch('/auth/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});"
        "if(resp.ok){window.location.assign(nextPath);return;}"
        "const data=await resp.json().catch(()=>({error:{message:'Login failed'}}));"
        "window.location.assign('/login?'+new URLSearchParams({next:nextPath,error:data.error?.message||'Login failed'}));"
        "});"
        "</script></div></body></html>"
    )


def _frontend_register_html(*, next_path: str, error: str | None = None) -> str:
    error_html = ""
    if error:
        error_html = f"<p class='error'>{escape(error)}</p>"
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Slack Mirror Register</title>"
        "<style>"
        "body{font-family:Arial,sans-serif;background:#f8fafc;color:#0f172a;margin:0;padding:48px}"
        ".card{max-width:460px;margin:0 auto;background:#fff;border:1px solid #dbe2ea;border-radius:16px;padding:28px;box-shadow:0 10px 30px rgba(15,23,42,.08)}"
        "h1{margin:0 0 10px;font-size:28px}"
        "label{display:block;margin:14px 0 6px;font-weight:600}"
        "input{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px}"
        "button{margin-top:18px;width:100%;padding:11px 14px;border:none;border-radius:10px;background:#0b57d0;color:#fff;font-weight:700;font-size:14px;cursor:pointer}"
        ".error{color:#b91c1c;background:#fef2f2;border:1px solid #fecaca;padding:10px 12px;border-radius:10px}"
        ".meta{margin-top:14px;color:#475569;font-size:14px}"
        "</style></head><body>"
        "<div class='card'>"
        "<h1>Create access</h1>"
        "<p>Register a local account for the Slack Mirror browser surfaces.</p>"
        f"{error_html}"
        "<form id='register-form'>"
        "<label for='username'>Username</label>"
        "<input id='username' name='username' autocomplete='username' required />"
        "<label for='display_name'>Display name</label>"
        "<input id='display_name' name='display_name' autocomplete='name' />"
        "<label for='password'>Password</label>"
        "<input id='password' name='password' type='password' autocomplete='new-password' required />"
        "<button type='submit'>Register</button>"
        "</form>"
        f"<p class='meta'>Already have an account? <a href=\"/login?{urlencode({'next': next_path})}\">Sign in</a></p>"
        "<script>"
        f"const nextPath={json.dumps(next_path)};"
        "document.getElementById('register-form').addEventListener('submit', async (event) => {"
        "event.preventDefault();"
        "const form=event.currentTarget;"
        "const payload={username:form.username.value,display_name:form.display_name.value,password:form.password.value};"
        "const resp=await fetch('/auth/register',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});"
        "if(resp.ok){window.location.assign(nextPath);return;}"
        "const data=await resp.json().catch(()=>({error:{message:'Registration failed'}}));"
        "window.location.assign('/register?'+new URLSearchParams({next:nextPath,error:data.error?.message||'Registration failed'}));"
        "});"
        "</script></div></body></html>"
    )


def _runtime_reports_index_html(reports: list[dict[str, Any]]) -> str:
    header_links = ""
    if reports:
        header_links = (
            "<div class='latest-links'>"
            "<a href=\"/runtime/reports/latest\">open latest</a> "
            "<a href=\"/v1/runtime/reports/latest\">latest manifest</a>"
            "</div>"
        )
        rows_parts: list[str] = []
        for index, report in enumerate(reports):
            is_latest = index == 0
            row_class = " class='latest-row'" if is_latest else ""
            latest_badge = " <span class='badge'>latest</span>" if is_latest else ""
            html_href = "/runtime/reports/latest" if is_latest else str(report["html_url"])
            rows_parts.append(
                f"<tr{row_class}>"
                f"<td><a href=\"{escape(html_href, quote=True)}\">{escape(str(report.get('name') or 'unknown'))}</a>{latest_badge}</td>"
                f"<td>{escape(str(report.get('status') or 'unknown'))}</td>"
                f"<td>{escape(str(report.get('summary') or ''))}</td>"
                f"<td><code>{escape(str(report.get('fetched_at') or ''))}</code></td>"
                f"<td><a href=\"{escape(str(report['markdown_url']), quote=True)}\">md</a> "
                f"<a href=\"{escape(str(report['json_url']), quote=True)}\">json</a></td>"
                "</tr>"
            )
        rows = "".join(rows_parts)
        table = (
            "<table><thead><tr><th>Name</th><th>Status</th><th>Summary</th><th>Fetched</th><th>Links</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        table = "<p>No managed runtime reports are available yet.</p>"

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Slack Mirror Runtime Reports</title>"
        "<style>"
        "body{font-family:Arial,sans-serif;margin:24px;background:#f8fafc;color:#0f172a}"
        "h1{margin:0 0 12px}"
        "p{line-height:1.5}"
        ".latest-links{margin:0 0 16px}"
        ".latest-links a{margin-right:12px;font-weight:600}"
        "table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #dbe2ea;border-radius:12px;overflow:hidden}"
        "th,td{padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:left;vertical-align:top}"
        "th{background:#e2e8f0}"
        "tr:last-child td{border-bottom:none}"
        ".latest-row td{background:#eff6ff}"
        ".badge{display:inline-block;margin-left:8px;padding:2px 8px;border-radius:999px;background:#0b57d0;color:#fff;font-size:12px;font-weight:700;vertical-align:middle}"
        "a{color:#0b57d0;text-decoration:none}"
        "a:hover{text-decoration:underline}"
        "code{background:#e2e8f0;padding:1px 5px;border-radius:6px}"
        "</style></head><body>"
        "<h1>Slack Mirror Runtime Reports</h1>"
        "<p>Latest managed runtime snapshots published by <code>user-env snapshot-report</code>. The newest report is highlighted and linked through the stable <code>/runtime/reports/latest</code> alias.</p>"
        f"{header_links}"
        f"{table}"
        "</body></html>"
    )


def _preview_html(path: Path, source_url: str) -> str:
    content_type, _ = mimetypes.guess_type(str(path))
    content_type = content_type or "application/octet-stream"
    title = escape(path.name)
    safe_url = escape(source_url, quote=True)
    if content_type.startswith("image/"):
        viewer = f"<img src=\"{safe_url}\" alt=\"{title}\" style=\"max-width:100%;height:auto;border:1px solid #d1d5db;border-radius:8px\" />"
    elif content_type == "application/pdf":
        viewer = f"<iframe src=\"{safe_url}\" title=\"{title}\" style=\"width:100%;height:88vh;border:1px solid #d1d5db;border-radius:8px\"></iframe>"
    elif content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        import mammoth

        with path.open("rb") as handle:
            result = mammoth.convert_to_html(handle)
        message_html = ""
        if result.messages:
            items = "".join(f"<li>{escape(str(message.message))}</li>" for message in result.messages)
            message_html = (
                "<aside style=\"margin-bottom:16px;padding:12px 14px;border:1px solid #e5e7eb;border-radius:8px;background:#fff7ed\">"
                "<strong>DOCX preview notes</strong><ul style=\"margin:8px 0 0 20px\">"
                f"{items}</ul></aside>"
            )
        viewer = (
            f"{message_html}<article style=\"border:1px solid #d1d5db;border-radius:8px;padding:20px;background:#fff\">"
            f"{result.value}</article>"
        )
    elif content_type in {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.oasis.opendocument.presentation",
        "application/vnd.oasis.opendocument.spreadsheet",
    }:
        from slack_mirror.sync.derived_text import render_office_preview_html

        rendered = render_office_preview_html(path)
        if not rendered:
            raise ValueError(f"Preview not supported for {content_type}")
        viewer = rendered
    elif content_type == "text/html":
        raw_html = path.read_text(encoding="utf-8", errors="replace")
        viewer = (
            f"<iframe sandbox=\"allow-same-origin\" srcdoc=\"{escape(raw_html, quote=True)}\" "
            "style=\"width:100%;height:88vh;border:1px solid #d1d5db;border-radius:8px;background:#fff\"></iframe>"
        )
    elif content_type.startswith("text/") or content_type in {"application/json", "application/xml"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        viewer = (
            "<pre style=\"white-space:pre-wrap;word-break:break-word;border:1px solid #d1d5db;"
            "border-radius:8px;padding:16px;background:#f8fafc;max-height:88vh;overflow:auto\">"
            f"{escape(text)}"
            "</pre>"
        )
    else:
        raise ValueError(f"Preview not supported for {content_type}")

    return (
        "<!doctype html>"
        "<html><head><meta charset='utf-8'>"
        f"<title>Preview: {title}</title>"
        "<style>"
        "body{font-family:Arial,sans-serif;margin:24px;background:#fff;color:#111827}"
        "header{margin-bottom:16px}"
        "a{color:#0b57d0}"
        "</style></head><body>"
        f"<header><h1 style='font-size:18px;margin:0 0 8px'>{title}</h1>"
        f"<div><a href=\"{safe_url}\" target=\"_blank\" rel=\"noopener\">Open raw file</a></div></header>"
        f"{viewer}</body></html>"
    )


def _parse_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    raw_len = int(handler.headers.get("Content-Length", "0"))
    if raw_len <= 0:
        return {}
    body = handler.rfile.read(raw_len)
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def create_api_server(*, bind: str, port: int, config_path: str | None = None) -> ThreadingHTTPServer:
    service = get_app_service(config_path)
    config = load_config(config_path)
    auth_config = service.frontend_auth_config()
    export_root = resolve_export_root(config)
    export_base_urls = resolve_export_base_urls(config)
    runtime_report_dir = runtime_report_dir_for_config(config_path)

    def runtime_report_links(name: str) -> dict[str, str]:
        safe_name = _safe_runtime_report_name(name)
        return {
            "html_url": f"/runtime/reports/{safe_name}",
            "markdown_url": f"/runtime/reports/{safe_name}.latest.md",
            "json_url": f"/runtime/reports/{safe_name}.latest.json",
        }

    class Handler(BaseHTTPRequestHandler):
        def _query(self) -> dict[str, list[str]]:
            return parse_qs(urlparse(self.path).query)

        def _path(self) -> str:
            raw = urlparse(self.path).path or "/"
            if raw.startswith("/exports/"):
                return raw
            return raw.rstrip("/") or "/"

        def _request_path_with_query(self) -> str:
            parsed = urlparse(self.path)
            if not parsed.query:
                return parsed.path or "/"
            return f"{parsed.path or '/'}?{parsed.query}"

        def _frontend_auth_session(self) -> FrontendAuthSession:
            cookie_value = _parse_cookie_value(self, auth_config.cookie_name)
            conn = service.connect()
            return service.frontend_auth_session(conn, session_token=cookie_value)

        def _is_protected_frontend_path(self, path: str) -> bool:
            if not auth_config.enabled:
                return False
            if path in {"/v1/health", "/login", "/register", "/logout", "/auth/status", "/auth/session", "/auth/login", "/auth/register", "/auth/logout"}:
                return False
            if path.startswith("/v1/workspaces/") and path.endswith("/webhook"):
                return False
            protected_prefixes = (
                "/exports",
                "/v1/exports",
                "/runtime/reports",
                "/v1/runtime/reports",
                "/v1/runtime/status",
                "/v1/runtime/live-validation",
            )
            return any(path == prefix or path.startswith(f"{prefix}/") for prefix in protected_prefixes)

        def _enforce_frontend_auth(self, path: str) -> FrontendAuthSession | None:
            if not self._is_protected_frontend_path(path):
                return FrontendAuthSession(authenticated=False, auth_source="unprotected")
            auth_session = self._frontend_auth_session()
            if auth_session.authenticated:
                return auth_session
            if path.startswith("/v1/"):
                _error_response(self, 401, "AUTH_REQUIRED", "Authentication required")
                return None
            destination = f"/login?{urlencode({'next': self._request_path_with_query()})}"
            _redirect_response(self, destination)
            return None

        def _issue_frontend_auth_cookie(self, *, session_token: str) -> None:
            _set_cookie_headers(
                self,
                key=auth_config.cookie_name,
                value=session_token,
                max_age=auth_config.session_days * 24 * 60 * 60,
                secure=auth_config.cookie_secure,
            )

        def _clear_frontend_auth_cookie(self) -> None:
            _set_cookie_headers(
                self,
                key=auth_config.cookie_name,
                value="",
                max_age=0,
                secure=auth_config.cookie_secure,
            )

        def _workspace_status(self, workspace: str, query: dict[str, list[str]]) -> None:
            conn = service.connect()
            summary, rows = service.get_workspace_status(
                conn,
                workspace=workspace,
                stale_hours=float(query.get("stale_hours", [24.0])[0]),
                max_zero_msg=int(query.get("max_zero_msg", [0])[0]),
                max_stale=int(query.get("max_stale", [0])[0]),
                enforce_stale=(query.get("enforce_stale", ["0"])[0] in {"1", "true", "yes"}),
            )
            _json_response(
                self,
                200,
                {"ok": True, "summary": summary.__dict__, "rows": [row.__dict__ for row in rows]},
            )

        def do_GET(self):  # noqa: N802
            path = self._path()
            query = self._query()

            auth_session = self._enforce_frontend_auth(path)
            if auth_session is None:
                return

            if path == "/v1/health":
                _json_response(self, 200, {"ok": True})
                return

            if path == "/auth/status":
                conn = service.connect()
                _json_response(self, 200, {"ok": True, "auth": service.frontend_auth_status(conn)})
                return

            if path == "/auth/session":
                session_payload = self._frontend_auth_session()
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "session": {
                            "authenticated": session_payload.authenticated,
                            "user_id": session_payload.user_id,
                            "username": session_payload.username,
                            "display_name": session_payload.display_name,
                            "session_id": session_payload.session_id,
                            "auth_source": session_payload.auth_source,
                            "expires_at": session_payload.expires_at,
                        },
                    },
                )
                return

            if path == "/login":
                next_path = str(query.get("next", ["/runtime/reports/latest"])[0] or "/runtime/reports/latest")
                error = str(query.get("error", [""])[0] or "").strip() or None
                if auth_session.authenticated:
                    _redirect_response(self, next_path)
                    return
                _html_response(
                    self,
                    200,
                    _frontend_login_html(
                        next_path=next_path,
                        error=error,
                        can_register=auth_config.allow_registration,
                    ),
                )
                return

            if path == "/register":
                next_path = str(query.get("next", ["/runtime/reports/latest"])[0] or "/runtime/reports/latest")
                error = str(query.get("error", [""])[0] or "").strip() or None
                if auth_session.authenticated:
                    _redirect_response(self, next_path)
                    return
                if not auth_config.enabled or not auth_config.allow_registration:
                    _error_response(self, 403, "REGISTRATION_DISABLED", "Registration is disabled")
                    return
                _html_response(self, 200, _frontend_register_html(next_path=next_path, error=error))
                return

            if path == "/logout":
                conn = service.connect()
                service.logout_frontend_user(conn, session_token=_parse_cookie_value(self, auth_config.cookie_name))
                self.send_response(303)
                self._clear_frontend_auth_cookie()
                self.send_header("location", "/login")
                self.send_header("content-length", "0")
                self.end_headers()
                return

            if path == "/v1/workspaces":
                conn = service.connect()
                _json_response(self, 200, {"ok": True, "workspaces": service.list_workspaces(conn)})
                return

            if path == "/v1/runtime/live-validation":
                require_live_units = query.get("require_live_units", ["1"])[0] in {"1", "true", "yes"}
                payload = service.validate_live_runtime(require_live_units=require_live_units)
                _json_response(self, 200 if payload.ok else 503, {"ok": payload.ok, "validation": payload.__dict__})
                return

            if path == "/v1/runtime/status":
                payload = service.runtime_status()
                _json_response(self, 200 if payload.ok else 503, {"ok": payload.ok, "status": payload.__dict__})
                return

            if path == "/v1/runtime/reports":
                payload = service.list_runtime_reports()
                reports = [{**item, **runtime_report_links(str(item.get("name") or ""))} for item in payload.reports]
                _json_response(self, 200, {"ok": True, "reports": reports})
                return

            if path == "/v1/runtime/reports/latest":
                payload = service.latest_runtime_report()
                if payload is None:
                    _error_response(self, 404, "NOT_FOUND", "No runtime reports available")
                    return
                _json_response(self, 200, {"ok": True, "report": {**payload, **runtime_report_links(str(payload.get('name') or ''))}})
                return

            if path == "/runtime/reports":
                payload = service.list_runtime_reports()
                reports = [{**item, **runtime_report_links(str(item.get("name") or ""))} for item in payload.reports]
                _html_response(self, 200, _runtime_reports_index_html(reports))
                return

            if path == "/runtime/reports/latest":
                payload = service.latest_runtime_report()
                if payload is None:
                    _error_response(self, 404, "NOT_FOUND", "No runtime reports available")
                    return
                safe_name = _safe_runtime_report_name(str(payload.get("name") or ""))
                target = runtime_report_dir / f"{safe_name}.latest.html"
                if not target.exists() or not target.is_file():
                    _error_response(self, 404, "NOT_FOUND", f"Runtime report not found: {safe_name}")
                    return
                _file_response(self, target)
                return

            m = re.fullmatch(r"/v1/runtime/reports/([^/]+)", path)
            if m:
                try:
                    payload = service.get_runtime_report(m.group(1))
                except ValueError as exc:
                    _error_response(self, 400, "BAD_REQUEST", str(exc))
                    return
                if payload is None:
                    _error_response(self, 404, "NOT_FOUND", f"Runtime report not found: {m.group(1)}")
                    return
                _json_response(self, 200, {"ok": True, "report": {**payload, **runtime_report_links(str(payload.get('name') or ''))}})
                return

            m = re.fullmatch(r"/runtime/reports/([^/]+)\.latest\.(html|md|json)", path)
            if m:
                try:
                    safe_name = _safe_runtime_report_name(m.group(1))
                except ValueError as exc:
                    _error_response(self, 400, "BAD_REQUEST", str(exc))
                    return
                suffix = m.group(2)
                target = runtime_report_dir / f"{safe_name}.latest.{suffix}"
                if not target.exists() or not target.is_file():
                    _error_response(self, 404, "NOT_FOUND", f"Runtime report file not found: {safe_name}.latest.{suffix}")
                    return
                _file_response(self, target)
                return

            m = re.fullmatch(r"/runtime/reports/([^/]+)", path)
            if m:
                try:
                    safe_name = _safe_runtime_report_name(m.group(1))
                except ValueError as exc:
                    _error_response(self, 400, "BAD_REQUEST", str(exc))
                    return
                target = runtime_report_dir / f"{safe_name}.latest.html"
                if not target.exists() or not target.is_file():
                    _error_response(self, 404, "NOT_FOUND", f"Runtime report not found: {safe_name}")
                    return
                _file_response(self, target)
                return

            if path == "/v1/exports":
                audience = str(query.get("audience", ["local"])[0])
                payload = list_export_manifests(export_root, base_urls=export_base_urls, default_audience=audience)
                _json_response(self, 200, {"ok": True, "exports": payload})
                return

            m = re.fullmatch(r"/v1/exports/([^/]+)", path)
            if m:
                export_id = m.group(1)
                audience = str(query.get("audience", ["local"])[0])
                bundle_dir = export_root / export_id
                if not bundle_dir.exists() or not bundle_dir.is_dir():
                    _error_response(self, 404, "NOT_FOUND", f"Export bundle not found: {export_id}")
                    return
                payload = build_export_manifest(
                    bundle_dir,
                    export_id=export_id,
                    base_urls=export_base_urls,
                    default_audience=audience,
                )
                _json_response(self, 200, {"ok": True, "export": payload})
                return

            m = re.fullmatch(r"/exports/([^/]+)/?", path)
            if m:
                export_id = m.group(1)
                try:
                    target = safe_export_path(export_root, export_id, "index.html")
                except ValueError as exc:
                    _error_response(self, 400, "BAD_REQUEST", str(exc))
                    return
                if not target.exists() or not target.is_file():
                    _error_response(self, 404, "NOT_FOUND", f"Export report not found: {export_id}/index.html")
                    return
                _file_response(self, target)
                return

            m = re.fullmatch(r"/exports/([^/]+)/(.+?)/preview", path)
            if m:
                export_id = m.group(1)
                relpath = m.group(2)
                try:
                    target = safe_export_path(export_root, export_id, relpath)
                except ValueError as exc:
                    _error_response(self, 400, "BAD_REQUEST", str(exc))
                    return
                if not target.exists() or not target.is_file():
                    _error_response(self, 404, "NOT_FOUND", f"Export file not found: {export_id}/{relpath}")
                    return
                try:
                    source_url = f"/exports/{export_id}/{relpath}"
                    _html_response(self, 200, _preview_html(target, source_url))
                except ValueError as exc:
                    _error_response(self, 415, "PREVIEW_UNSUPPORTED", str(exc))
                return

            m = re.fullmatch(r"/exports/([^/]+)/(.+)", path)
            if m:
                export_id = m.group(1)
                relpath = m.group(2)
                try:
                    target = safe_export_path(export_root, export_id, relpath)
                except ValueError as exc:
                    _error_response(self, 400, "BAD_REQUEST", str(exc))
                    return
                if not target.exists() or not target.is_file():
                    _error_response(self, 404, "NOT_FOUND", f"Export file not found: {export_id}/{relpath}")
                    return
                _file_response(self, target)
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/status", path)
            if m:
                self._workspace_status(m.group(1), query)
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/listeners", path)
            if m:
                conn = service.connect()
                try:
                    payload = service.list_listeners(conn, workspace=m.group(1))
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, workspace=m.group(1), operation="listeners.list")
                    return
                _json_response(self, 200, {"ok": True, "listeners": payload})
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/listeners/(\d+)", path)
            if m:
                conn = service.connect()
                try:
                    payload = service.get_listener_status(conn, workspace=m.group(1), listener_id=int(m.group(2)))
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(
                        self,
                        exc,
                        path=path,
                        workspace=m.group(1),
                        listener_id=int(m.group(2)),
                        operation="listeners.status",
                    )
                    return
                _json_response(self, 200, {"ok": True, "listener": payload})
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/deliveries", path)
            if m:
                conn = service.connect()
                try:
                    listener_id = query.get("listener_id", [None])[0]
                    status = query.get("status", ["pending"])[0]
                    payload = service.list_listener_deliveries(
                        conn,
                        workspace=m.group(1),
                        status=status,
                        listener_id=int(listener_id) if listener_id else None,
                        limit=int(query.get("limit", [100])[0]),
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, workspace=m.group(1), operation="deliveries.list")
                    return
                _json_response(self, 200, {"ok": True, "deliveries": payload})
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/search/corpus", path)
            if m:
                conn = service.connect()
                try:
                    payload = service.corpus_search(
                        conn,
                        workspace=m.group(1),
                        query=str(query.get("query", [""])[0]),
                        limit=int(query.get("limit", [20])[0]),
                        mode=str(query.get("mode", ["hybrid"])[0]),
                        model_id=str(query.get("model", ["local-hash-128"])[0]),
                        lexical_weight=float(query.get("lexical_weight", [0.6])[0]),
                        semantic_weight=float(query.get("semantic_weight", [0.4])[0]),
                        semantic_scale=float(query.get("semantic_scale", [10.0])[0]),
                        use_fts=query.get("no_fts", ["0"])[0] not in {"1", "true", "yes"},
                        derived_kind=query.get("kind", [None])[0],
                        derived_source_kind=query.get("source_kind", [None])[0],
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, workspace=m.group(1), operation="search.corpus")
                    return
                _json_response(self, 200, {"ok": True, "results": payload})
                return

            if path == "/v1/search/corpus":
                conn = service.connect()
                try:
                    payload = service.corpus_search(
                        conn,
                        all_workspaces=True,
                        query=str(query.get("query", [""])[0]),
                        limit=int(query.get("limit", [20])[0]),
                        mode=str(query.get("mode", ["hybrid"])[0]),
                        model_id=str(query.get("model", ["local-hash-128"])[0]),
                        lexical_weight=float(query.get("lexical_weight", [0.6])[0]),
                        semantic_weight=float(query.get("semantic_weight", [0.4])[0]),
                        semantic_scale=float(query.get("semantic_scale", [10.0])[0]),
                        use_fts=query.get("no_fts", ["0"])[0] not in {"1", "true", "yes"},
                        derived_kind=query.get("kind", [None])[0],
                        derived_source_kind=query.get("source_kind", [None])[0],
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="search.corpus")
                    return
                _json_response(self, 200, {"ok": True, "scope": "all", "results": payload})
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/search/readiness", path)
            if m:
                conn = service.connect()
                try:
                    payload = service.search_readiness(conn, workspace=m.group(1))
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, workspace=m.group(1), operation="search.readiness")
                    return
                _json_response(self, 200, {"ok": True, "readiness": payload})
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/search/health", path)
            if m:
                conn = service.connect()
                try:
                    payload = service.search_health(
                        conn,
                        workspace=m.group(1),
                        dataset_path=query.get("dataset", [None])[0],
                        mode=str(query.get("mode", ["hybrid"])[0]),
                        limit=int(query.get("limit", [10])[0]),
                        model_id=str(query.get("model", ["local-hash-128"])[0]),
                        min_hit_at_3=float(query.get("min_hit_at_3", [0.5])[0]),
                        min_hit_at_10=float(query.get("min_hit_at_10", [0.8])[0]),
                        min_ndcg_at_k=float(query.get("min_ndcg_at_k", [0.6])[0]),
                        max_latency_p95_ms=float(query.get("max_latency_p95_ms", [800.0])[0]),
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, workspace=m.group(1), operation="search.health")
                    return
                status = 200 if payload["status"] != "fail" else 503
                _json_response(self, status, {"ok": payload["status"] != "fail", "health": payload})
                return

            _error_response(self, 404, "NOT_FOUND", f"Unknown path: {path}")

        def do_POST(self):  # noqa: N802
            path = self._path()
            query = self._query()
            if self._is_protected_frontend_path(path):
                auth_session = self._enforce_frontend_auth(path)
                if auth_session is None:
                    return
            try:
                body = _parse_json_body(self)
            except json.JSONDecodeError as exc:
                _error_response(self, 400, "BAD_REQUEST", f"Invalid JSON: {exc}")
                return

            if path == "/auth/register":
                conn = service.connect()
                try:
                    issued = service.register_frontend_user(
                        conn,
                        username=str(body.get("username") or ""),
                        password=str(body.get("password") or ""),
                        display_name=str(body.get("display_name") or "") or None,
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="auth.register")
                    return
                payload = {
                    "authenticated": issued.payload.authenticated,
                    "user_id": issued.payload.user_id,
                    "username": issued.payload.username,
                    "display_name": issued.payload.display_name,
                    "session_id": issued.payload.session_id,
                    "auth_source": issued.payload.auth_source,
                    "expires_at": issued.payload.expires_at,
                }
                data = json.dumps({"ok": True, "session": payload}, indent=2).encode("utf-8")
                self.send_response(201)
                self._issue_frontend_auth_cookie(session_token=issued.session_token)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            if path == "/auth/login":
                conn = service.connect()
                try:
                    issued = service.login_frontend_user(
                        conn,
                        username=str(body.get("username") or ""),
                        password=str(body.get("password") or ""),
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="auth.login")
                    return
                payload = {
                    "authenticated": issued.payload.authenticated,
                    "user_id": issued.payload.user_id,
                    "username": issued.payload.username,
                    "display_name": issued.payload.display_name,
                    "session_id": issued.payload.session_id,
                    "auth_source": issued.payload.auth_source,
                    "expires_at": issued.payload.expires_at,
                }
                data = json.dumps({"ok": True, "session": payload}, indent=2).encode("utf-8")
                self.send_response(200)
                self._issue_frontend_auth_cookie(session_token=issued.session_token)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            if path == "/auth/logout":
                conn = service.connect()
                service.logout_frontend_user(conn, session_token=_parse_cookie_value(self, auth_config.cookie_name))
                data = json.dumps({"ok": True, "signed_out": True}, indent=2).encode("utf-8")
                self.send_response(200)
                self._clear_frontend_auth_cookie()
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/messages", path)
            if m:
                conn = service.connect()
                try:
                    payload = service.send_message(
                        conn,
                        workspace=m.group(1),
                        channel_ref=str(body.get("channel_ref") or body.get("channel") or ""),
                        text=str(body.get("text") or ""),
                        options={k: v for k, v in body.items() if k not in {"channel_ref", "channel", "text"}},
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, workspace=m.group(1), operation="messages.send")
                    return
                _json_response(self, 200, {"ok": True, "action": payload})
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/threads/([^/]+)/replies", path)
            if m:
                conn = service.connect()
                try:
                    payload = service.send_thread_reply(
                        conn,
                        workspace=m.group(1),
                        channel_ref=str(body.get("channel_ref") or body.get("channel") or ""),
                        thread_ref=m.group(2),
                        text=str(body.get("text") or ""),
                        options={k: v for k, v in body.items() if k not in {"channel_ref", "channel", "text"}},
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, workspace=m.group(1), thread_ref=m.group(2), operation="threads.reply")
                    return
                _json_response(self, 200, {"ok": True, "action": payload})
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/listeners", path)
            if m:
                conn = service.connect()
                try:
                    payload = service.register_listener(conn, workspace=m.group(1), spec=body)
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, workspace=m.group(1), operation="listeners.register")
                    return
                _json_response(self, 201, {"ok": True, "listener": payload})
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/deliveries/(\d+)/ack", path)
            if m:
                conn = service.connect()
                try:
                    service.ack_listener_delivery(
                        conn,
                        workspace=m.group(1),
                        delivery_id=int(m.group(2)),
                        status=str(body.get("status") or "delivered"),
                        error=body.get("error"),
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(
                        self,
                        exc,
                        path=path,
                        workspace=m.group(1),
                        delivery_id=int(m.group(2)),
                        operation="deliveries.ack",
                    )
                    return
                _json_response(self, 200, {"ok": True})
                return

            if path == "/v1/health":
                _json_response(self, 405, {"ok": False, "error": {"code": "METHOD_NOT_ALLOWED", "message": "GET only"}})
                return

            _error_response(self, 404, "NOT_FOUND", f"Unknown path: {path}")

        def do_DELETE(self):  # noqa: N802
            path = self._path()
            m = re.fullmatch(r"/v1/workspaces/([^/]+)/listeners/(\d+)", path)
            if m:
                conn = service.connect()
                try:
                    service.unregister_listener(conn, workspace=m.group(1), listener_id=int(m.group(2)))
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(
                        self,
                        exc,
                        path=path,
                        workspace=m.group(1),
                        listener_id=int(m.group(2)),
                        operation="listeners.unregister",
                    )
                    return
                _json_response(self, 200, {"ok": True})
                return
            _error_response(self, 404, "NOT_FOUND", f"Unknown path: {path}")

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((bind, port), Handler)


def run_api_server(*, bind: str, port: int, config_path: str | None = None) -> None:
    server = create_api_server(bind=bind, port=port, config_path=config_path)
    print(f"API server listening on http://{bind}:{port}/v1")
    server.serve_forever()
