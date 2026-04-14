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


def _request_is_secure(
    handler: BaseHTTPRequestHandler,
    *,
    export_base_urls: dict[str, str] | None = None,
    include_browser_headers: bool = True,
) -> bool:
    forwarded_proto = str(handler.headers.get("x-forwarded-proto", "")).split(",", 1)[0].strip().lower()
    if forwarded_proto:
        return forwarded_proto == "https"

    if include_browser_headers:
        for header_name in ("origin", "referer"):
            header_value = str(handler.headers.get(header_name, "")).split(",", 1)[0].strip()
            if not header_value:
                continue
            parsed_header = urlparse(header_value)
            if parsed_header.scheme in {"http", "https"}:
                return parsed_header.scheme == "https"

    forwarded = str(handler.headers.get("forwarded", "")).strip()
    forwarded_host = ""
    if forwarded:
        proto_match = re.search(r"(?:^|[;,\s])proto=(https?)", forwarded, flags=re.IGNORECASE)
        if proto_match:
            return proto_match.group(1).lower() == "https"
        host_match = re.search(r"(?:^|[;,\s])host=\"?([^;,\"]+)\"?", forwarded, flags=re.IGNORECASE)
        if host_match:
            forwarded_host = host_match.group(1).strip().lower()

    forwarded_port = str(handler.headers.get("x-forwarded-port", "")).split(",", 1)[0].strip()
    if forwarded_port == "443":
        return True
    forwarded_ssl = str(handler.headers.get("x-forwarded-ssl", "")).split(",", 1)[0].strip().lower()
    if forwarded_ssl in {"on", "true", "1"}:
        return True

    hosts_to_check = [
        str(handler.headers.get("host", "")).strip().lower(),
        str(handler.headers.get("x-forwarded-host", "")).split(",", 1)[0].strip().lower(),
        str(handler.headers.get("x-original-host", "")).split(",", 1)[0].strip().lower(),
        forwarded_host,
    ]
    if export_base_urls:
        for candidate_host in hosts_to_check:
            if not candidate_host:
                continue
            candidate_hostname = candidate_host.split(":", 1)[0]
            for base_url in export_base_urls.values():
                parsed = urlparse(base_url)
                if parsed.hostname and candidate_hostname == parsed.hostname.lower():
                    return parsed.scheme.lower() == "https"
    return False


def _origin_from_header_value(value: str) -> str | None:
    raw = str(value or "").split(",", 1)[0].strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _allowed_request_origins(
    handler: BaseHTTPRequestHandler,
    *,
    export_base_urls: dict[str, str] | None = None,
) -> set[str]:
    allowed: set[str] = set()
    if export_base_urls:
        for base_url in export_base_urls.values():
            parsed = urlparse(base_url)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                allowed.add(f"{parsed.scheme.lower()}://{parsed.netloc.lower()}")
    host = str(handler.headers.get("host", "")).split(",", 1)[0].strip().lower()
    if host:
        scheme = (
            "https"
            if _request_is_secure(handler, export_base_urls=export_base_urls, include_browser_headers=False)
            else "http"
        )
        allowed.add(f"{scheme}://{host}")
    return allowed


def _validate_same_origin_post(
    handler: BaseHTTPRequestHandler,
    *,
    export_base_urls: dict[str, str] | None = None,
) -> str | None:
    observed_origin = _origin_from_header_value(handler.headers.get("origin", "")) or _origin_from_header_value(
        handler.headers.get("referer", "")
    )
    if not observed_origin:
        return "Missing Origin or Referer header"
    if observed_origin not in _allowed_request_origins(handler, export_base_urls=export_base_urls):
        return f"Cross-origin POST not allowed from {observed_origin}"
    return None


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
        "<label for='username'>Email or username</label>"
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


def _frontend_register_html(*, next_path: str, error: str | None = None, registration_allowlist: list[str] | tuple[str, ...] | None = None) -> str:
    error_html = ""
    if error:
        error_html = f"<p class='error'>{escape(error)}</p>"
    normalized_allowlist = [str(item).strip() for item in (registration_allowlist or []) if str(item).strip()]
    allowlist_panel = ""
    username_label = "Username"
    username_placeholder = ""
    intro = "<p>Register a local account for the Slack Mirror browser surfaces.</p>"
    if normalized_allowlist:
        username_label = "Allowed email or username"
        username_placeholder = normalized_allowlist[0]
        allowlist_items = "".join(f"<li><code>{escape(item)}</code></li>" for item in normalized_allowlist)
        noun = "identity" if len(normalized_allowlist) == 1 else "identities"
        intro = (
            "<p>Register a local account for the Slack Mirror browser surfaces. "
            f"This install only allows self-registration for specific {noun}.</p>"
        )
        allowlist_panel = (
            "<div class='policy'>"
            "<strong>Allowed registration identities</strong>"
            f"<ul>{allowlist_items}</ul>"
            "<p class='meta policy-copy'>Use one of the exact values above in the field below.</p>"
            "</div>"
        )
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
        ".policy{margin-top:14px;padding:12px 14px;border:1px solid #dbe2ea;border-radius:12px;background:#f8fafc}"
        ".policy ul{margin:10px 0 0 18px;padding:0}"
        ".policy li{margin:6px 0}"
        ".policy-copy{margin-top:10px}"
        "</style></head><body>"
        "<div class='card'>"
        "<h1>Create access</h1>"
        f"{intro}"
        f"{error_html}"
        f"{allowlist_panel}"
        "<form id='register-form'>"
        f"<label for='username'>{escape(username_label)}</label>"
        f"<input id='username' name='username' autocomplete='username' placeholder=\"{escape(username_placeholder, quote=True)}\" required />"
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


def _frontend_settings_html(
    *,
    auth_session: FrontendAuthSession,
    auth_status: dict[str, Any],
    sessions: list[dict[str, Any]],
) -> str:
    user_label = auth_session.display_name or auth_session.username or "Authenticated user"
    allowlist = auth_status.get("registration_allowlist") or []
    registration_policy = "open" if auth_status.get("registration_open") and not allowlist else "allowlisted"
    allowlist_html = (
        "".join(f"<li><code>{escape(str(item))}</code></li>" for item in allowlist)
        if allowlist
        else "<li>No explicit allowlist.</li>"
    )

    session_rows = []
    for item in sessions:
        session_id = int(item.get("session_id", 0) or 0)
        is_current = auth_session.session_id == session_id
        is_active = bool(item.get("active"))
        state_badge = (
            "<span class='badge badge-ok'>current</span>"
            if is_current and is_active
            else "<span class='badge badge-ok'>active</span>"
            if is_active
            else "<span class='badge badge-warn'>inactive</span>"
        )
        revoke_control = (
            f"<button class='danger' data-session-id='{session_id}' data-current={'true' if is_current else 'false'}>"
            + ("Sign out here" if is_current else "Revoke")
            + "</button>"
            if is_active
            else "<span class='meta'>Already inactive</span>"
        )
        session_rows.append(
            f"<li class='session-row' data-session-id='{session_id}'>"
            f"<div class='session-main'><div class='session-heading'><strong>Session {session_id}</strong> <span class='session-state'>{state_badge}</span></div>"
            f"<div class='meta'>source <code>{escape(str(item.get('auth_source') or 'unknown'))}</code> · created <code>{escape(str(item.get('created_at') or ''))}</code></div>"
            f"<div class='meta'>last seen <code>{escape(str(item.get('last_seen_at') or ''))}</code> · expires <code>{escape(str(item.get('expires_at') or ''))}</code></div></div>"
            f"<div class='session-actions'>{revoke_control}</div>"
            "</li>"
        )
    if not session_rows:
        session_rows.append("<li class='empty'>No browser sessions found.</li>")

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Slack Mirror Settings</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<style>"
        ":root{--bg:#f4efe7;--panel:#fffdf9;--ink:#122033;--muted:#5f6c7b;--line:#d9d0c3;--accent:#0b57d0;--bad:#a12828;--bad-soft:#fde5e5;--ok:#1f7a44;--ok-soft:#ddefe3;--warn:#a05a00;--warn-soft:#fff0db;--shadow:0 14px 30px rgba(18,32,51,.08);}"
        "*{box-sizing:border-box}body{margin:0;font-family:\"Aptos\",\"Segoe UI\",Arial,sans-serif;background:linear-gradient(180deg,#f6f1e9 0,#efe7dc 100%);color:var(--ink)}"
        ".shell{max-width:1080px;margin:0 auto;padding:28px 18px 40px}.top{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:18px}"
        ".card{background:var(--panel);border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:22px}"
        ".grid{display:grid;grid-template-columns:1fr 1.3fr;gap:18px}.stack{display:grid;gap:18px}"
        "h1{margin:8px 0 8px;font-size:34px}.eyebrow{display:inline-block;padding:6px 10px;border-radius:999px;background:#ebe4d8;color:#514739;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase}"
        "h2{margin:0 0 12px;font-size:19px}.meta{color:var(--muted);font-size:13px;line-height:1.45}"
        "a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}"
        ".btn{display:inline-flex;align-items:center;gap:8px;padding:11px 14px;border-radius:14px;border:1px solid #b7c9ee;background:#edf4ff;color:var(--accent);font-weight:700}"
        ".btn.secondary{background:#f8f5ef;border-color:var(--line);color:var(--ink)}"
        "ul{list-style:none;margin:0;padding:0;display:grid;gap:12px}.list-row,.session-row{padding:14px 16px;border:1px solid #e4ddd1;border-radius:16px;background:#fcfaf6}"
        ".session-row{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.session-heading{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.session-actions{display:flex;align-items:center}.empty{padding:16px;border:1px dashed #d6cbbb;border-radius:16px;color:var(--muted);background:#fbf7f0}"
        ".badge{display:inline-flex;align-items:center;padding:4px 9px;border-radius:999px;font-size:12px;font-weight:700;line-height:1;margin-left:8px}.badge-ok{background:var(--ok-soft);color:var(--ok)}.badge-warn{background:var(--warn-soft);color:var(--warn)}"
        "code{background:#efe7da;border:1px solid #dfd3c2;padding:2px 6px;border-radius:8px;font-size:12px}"
        "button.danger{padding:10px 12px;border:none;border-radius:12px;background:var(--bad-soft);color:var(--bad);font-weight:700;cursor:pointer}"
        ".status-chip{display:inline-flex;align-items:center;padding:4px 10px;border-radius:999px;background:#ebe4d8;color:#514739;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}"
        "#feedback{display:none;margin-top:12px;padding:12px 14px;border-radius:14px;font-size:14px}.feedback-ok{display:block;background:var(--ok-soft);color:var(--ok)}.feedback-bad{display:block;background:var(--bad-soft);color:var(--bad)}"
        "@media (max-width: 860px){.grid{grid-template-columns:1fr}.top,.session-row{flex-direction:column}.session-actions{width:100%}button.danger{width:100%}}"
        "</style></head><body><div class='shell'>"
        "<div class='top'>"
        "<div><span class='eyebrow'>Slack Mirror</span>"
        "<h1>Account settings</h1>"
        f"<div class='meta'>Signed in as <strong>{escape(user_label)}</strong> · username <code>{escape(str(auth_session.username or ''))}</code></div></div>"
        "<div style='display:flex;gap:10px;flex-wrap:wrap'>"
        "<a class='btn secondary' href='/'>Home</a>"
        "<a class='btn secondary' href='/runtime/reports'>Runtime reports</a>"
        "<a class='btn' href='/logout'>Logout</a>"
        "</div></div>"
        "<div class='grid'>"
        "<div class='stack'>"
        "<section class='card'>"
        "<h2>Registration policy</h2>"
        f"<div class='meta'>Self-registration is <span class='status-chip'>{escape(registration_policy)}</span></div>"
        f"<div class='meta' style='margin-top:10px'>open registration <code>{escape(str(bool(auth_status.get('registration_open'))))}</code> · allowlist count <code>{escape(str(auth_status.get('registration_allowlist_count') or 0))}</code></div>"
        "<ul style='margin-top:14px'>"
        f"{allowlist_html}"
        "</ul>"
        "</section>"
        "<section class='card'>"
        "<h2>Session API</h2>"
        "<ul>"
        "<li class='list-row'><a href='/auth/session'><code>/auth/session</code></a></li>"
        "<li class='list-row'><a href='/auth/sessions'><code>/auth/sessions</code></a></li>"
        "</ul>"
        "</section>"
        "</div>"
        "<section class='card'>"
        "<h2>Browser sessions</h2>"
        "<div class='meta'>Revoke any active session owned by this account. Revoking the current session signs this browser out immediately.</div>"
        "<div id='feedback'></div>"
        f"<ul id='session-list' style='margin-top:14px'>{''.join(session_rows)}</ul>"
        "</section>"
        "</div>"
        "<script>"
        "const feedback=document.getElementById('feedback');"
        "function showFeedback(message,isError){feedback.textContent=message;feedback.className=isError?'feedback-bad':'feedback-ok';}"
        "function markSessionInactive(sessionId,current){"
        "const row=document.querySelector(`.session-row[data-session-id=\"${sessionId}\"]`);"
        "if(!row)return;"
        "const state=row.querySelector('.session-state');"
        "if(state){state.innerHTML='<span class=\"badge badge-warn\">inactive</span>';}"
        "const actions=row.querySelector('.session-actions');"
        "if(actions){actions.innerHTML=current?'<span class=\"meta\">Signed out in this browser</span>':'<span class=\"meta\">Already inactive</span>';}"
        "}"
        "for(const button of document.querySelectorAll('button[data-session-id]')){button.addEventListener('click',async()=>{"
        "const sessionId=button.getAttribute('data-session-id');"
        "const current=button.getAttribute('data-current')==='true';"
        "button.disabled=true;"
        "const resp=await fetch(`/auth/sessions/${sessionId}/revoke`,{method:'POST',headers:{'content-type':'application/json'},body:'{}'});"
        "if(resp.ok){markSessionInactive(sessionId,current);showFeedback(current?`Signed out session ${sessionId}. Redirecting to login...`:`Revoked session ${sessionId}.`,false);if(current){window.location.assign('/login');}return;}"
        "const data=await resp.json().catch(()=>({error:{message:'Revocation failed'}}));"
        "showFeedback(data.error?.message||'Revocation failed',true);button.disabled=false;});}"
        "</script>"
        "</div></body></html>"
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


def _landing_page_html(
    *,
    auth_session: FrontendAuthSession,
    runtime_status: dict[str, Any],
    latest_report: dict[str, Any] | None,
    reports: list[dict[str, Any]],
    exports: list[dict[str, Any]],
) -> str:
    status_payload = runtime_status.get("status", {})
    services = status_payload.get("services") or {}
    reconcile_workspaces = status_payload.get("reconcile_workspaces") or []
    services_active = sum(1 for state in services.values() if state == "active")
    warnings = sum(int(item.get("warnings", 0) or 0) for item in reconcile_workspaces)
    failures = sum(int(item.get("failed", 0) or 0) for item in reconcile_workspaces)
    user_label = auth_session.display_name or auth_session.username or "Authenticated user"

    def code(text: Any) -> str:
        return f"<code>{escape(str(text))}</code>"

    def badge(label: str, tone: str = "neutral") -> str:
        return f"<span class='badge badge-{tone}'>{escape(label)}</span>"

    health_badges = []
    health_badges.append(badge("healthy" if runtime_status.get("ok") else "degraded", "ok" if runtime_status.get("ok") else "warn"))
    if failures:
        health_badges.append(badge(f"{failures} reconcile failed", "bad"))
    elif warnings:
        health_badges.append(badge(f"{warnings} reconcile warnings", "warn"))
    else:
        health_badges.append(badge("reconcile clean", "ok"))
    latest_summary = escape(str((latest_report or {}).get("summary") or "No runtime snapshot published yet"))

    report_items = []
    for report in reports:
        name = str(report.get("name") or "unknown")
        report_items.append(
            "<li class='list-row'>"
            f"<div><a href=\"/runtime/reports/{escape(name, quote=True)}\">{escape(name)}</a> "
            f"{badge(str(report.get('status') or 'unknown'), 'ok' if str(report.get('status') or '') == 'pass' else 'warn')}</div>"
            f"<div class='meta'>{escape(str(report.get('summary') or ''))}</div>"
            f"<div class='meta'>{code(report.get('fetched_at') or '')}</div>"
            "</li>"
        )
    if not report_items:
        report_items.append("<li class='empty'>No runtime reports yet.</li>")

    export_items = []
    for item in exports:
        export_id = str(item.get("export_id") or "unknown")
        workspace = str(item.get("workspace") or "unknown")
        channel = str(item.get("channel") or item.get("channel_id") or "unknown")
        export_items.append(
            "<li class='list-row'>"
            f"<div><a href=\"/exports/{escape(export_id, quote=True)}\">{escape(export_id)}</a></div>"
            f"<div class='meta'>{badge(str(item.get('kind') or 'export'), 'neutral')} {code(workspace)} {code(channel)}</div>"
            f"<div class='meta'>{escape(str(item.get('day') or ''))} · {int(item.get('attachment_count', 0) or 0)} attachments · {int(item.get('file_count', 0) or 0)} files</div>"
            "</li>"
        )
    if not export_items:
        export_items.append("<li class='empty'>No managed exports published yet.</li>")

    reconcile_rows = []
    for workspace in reconcile_workspaces:
        name = str(workspace.get("name") or "unknown")
        if workspace.get("state_present"):
            age = workspace.get("age_seconds")
            age_text = f"{int(age)}s ago" if age is not None else "age unknown"
            reconcile_rows.append(
                "<li class='list-row compact'>"
                f"<div>{badge(name, 'neutral')} downloaded {code(workspace.get('downloaded', 0))} "
                f"warnings {code(workspace.get('warnings', 0))} failed {code(workspace.get('failed', 0))}</div>"
                f"<div class='meta'>{escape(age_text)}</div>"
                "</li>"
            )
        else:
            reconcile_rows.append(
                "<li class='list-row compact'>"
                f"<div>{badge(name, 'neutral')} no reconcile state yet</div>"
                "</li>"
            )
    if not reconcile_rows:
        reconcile_rows.append("<li class='empty'>No reconcile state available.</li>")

    endpoint_rows = "".join(
        [
            f"<li class='list-row compact'><a href=\"/v1/runtime/status\">{code('/v1/runtime/status')}</a></li>",
            f"<li class='list-row compact'><a href=\"/v1/runtime/reports/latest\">{code('/v1/runtime/reports/latest')}</a></li>",
            f"<li class='list-row compact'><a href=\"/v1/exports\">{code('/v1/exports')}</a></li>",
            f"<li class='list-row compact'><a href=\"/auth/session\">{code('/auth/session')}</a></li>",
            f"<li class='list-row compact'><a href=\"/auth/sessions\">{code('/auth/sessions')}</a></li>",
            f"<li class='list-row compact'><a href=\"/settings\">{code('/settings')}</a></li>",
        ]
    )

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Slack Mirror</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<style>"
        ":root{--bg:#f4efe7;--panel:#fffdf9;--ink:#122033;--muted:#5f6c7b;--line:#d9d0c3;--accent:#0b57d0;--accent-soft:#dfeafe;--ok:#1f7a44;--ok-soft:#ddefe3;--warn:#a05a00;--warn-soft:#fff0db;--bad:#a12828;--bad-soft:#fde5e5;--shadow:0 14px 30px rgba(18,32,51,.08);}"
        "*{box-sizing:border-box} body{margin:0;font-family:\"Aptos\",\"Segoe UI\",Arial,sans-serif;background:radial-gradient(circle at top right,#fff8ef 0,transparent 28%),linear-gradient(180deg,#f6f1e9 0,#efe7dc 100%);color:var(--ink)}"
        "a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}"
        ".shell{max-width:1180px;margin:0 auto;padding:32px 20px 48px}"
        ".hero{display:grid;grid-template-columns:2.2fr 1fr;gap:18px;margin-bottom:18px}"
        ".card{background:var(--panel);border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:22px}"
        ".hero-card{padding:28px}"
        ".eyebrow{display:inline-block;padding:6px 10px;border-radius:999px;background:#ebe4d8;color:#514739;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase}"
        "h1{margin:14px 0 10px;font-size:40px;line-height:1.05}"
        ".lede{margin:0;color:var(--muted);font-size:16px;line-height:1.55;max-width:52rem}"
        ".hero-actions,.top-links{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}"
        ".btn{display:inline-flex;align-items:center;gap:8px;padding:11px 14px;border-radius:14px;border:1px solid #b7c9ee;background:#edf4ff;color:var(--accent);font-weight:700}"
        ".btn.secondary{background:#f8f5ef;border-color:var(--line);color:var(--ink)}"
        ".mini-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:18px}"
        ".metric{padding:14px;border-radius:16px;background:#f7f2ea;border:1px solid #e2d8ca}"
        ".metric .label{display:block;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}"
        ".metric .value{font-size:28px;font-weight:800;line-height:1.1}"
        ".meta{color:var(--muted);font-size:13px;line-height:1.45}"
        ".grid{display:grid;grid-template-columns:1.3fr 1fr;gap:18px}"
        ".stack{display:grid;gap:18px}"
        ".section-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px}"
        "h2{margin:0;font-size:19px}"
        "ul{list-style:none;padding:0;margin:0;display:grid;gap:10px}"
        ".list-row{padding:14px 16px;border:1px solid #e4ddd1;border-radius:16px;background:#fcfaf6}"
        ".list-row.compact{padding:12px 14px}"
        ".empty{padding:16px;border:1px dashed #d6cbbb;border-radius:16px;color:var(--muted);background:#fbf7f0}"
        ".badge{display:inline-flex;align-items:center;padding:4px 9px;border-radius:999px;font-size:12px;font-weight:700;line-height:1;margin-right:6px}"
        ".badge-neutral{background:#ece7dc;color:#514739}.badge-ok{background:var(--ok-soft);color:var(--ok)}.badge-warn{background:var(--warn-soft);color:var(--warn)}.badge-bad{background:var(--bad-soft);color:var(--bad)}"
        "code{background:#efe7da;border:1px solid #dfd3c2;padding:2px 6px;border-radius:8px;font-size:12px}"
        ".status-line{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}"
        ".service-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:10px}"
        ".service-pill{padding:10px 12px;border-radius:14px;background:#f7f2ea;border:1px solid #e2d8ca}"
        "@media (max-width: 900px){.hero,.grid{grid-template-columns:1fr}.mini-grid,.service-list{grid-template-columns:1fr 1fr}}"
        "@media (max-width: 640px){.shell{padding:20px 14px 32px}h1{font-size:32px}.mini-grid,.service-list{grid-template-columns:1fr}}"
        "</style></head><body><div class='shell'>"
        "<div class='hero'>"
        "<section class='card hero-card'>"
        "<span class='eyebrow'>Slack Mirror</span>"
        "<h1>Authenticated workspace home</h1>"
        f"<p class='lede'>Signed in as <strong>{escape(user_label)}</strong>. Use this page as the browser entrypoint for runtime health, the freshest ops snapshot, and recent managed exports.</p>"
        f"<div class='status-line'>{''.join(health_badges)}</div>"
        "<div class='hero-actions'>"
        "<a class='btn' href='/runtime/reports/latest'>Latest runtime snapshot</a>"
        "<a class='btn secondary' href='/runtime/reports'>Runtime reports</a>"
        "<a class='btn secondary' href='/settings'>Settings</a>"
        "<a class='btn secondary' href='/v1/exports'>Export manifest API</a>"
        "<a class='btn secondary' href='/logout'>Logout</a>"
        "</div>"
        "<div class='mini-grid'>"
        f"<div class='metric'><span class='label'>Managed Services</span><span class='value'>{services_active}</span><div class='meta'>{len(services)} tracked service states</div></div>"
        f"<div class='metric'><span class='label'>Published Reports</span><span class='value'>{len(reports)}</span><div class='meta'>latest summary: {latest_summary}</div></div>"
        f"<div class='metric'><span class='label'>Recent Exports</span><span class='value'>{len(exports)}</span><div class='meta'>managed bundles visible from the current config</div></div>"
        "</div>"
        "</section>"
        "<aside class='card'>"
        "<div class='section-title'><h2>Runtime health</h2></div>"
        f"<div class='meta'>wrappers present {code(status_payload.get('wrappers_present', False))} · api service present {code(status_payload.get('api_service_present', False))}</div>"
        "<div class='service-list'>"
        + "".join(
            f"<div class='service-pill'><div>{code(name)}</div><div class='meta'>{escape(str(state))}</div></div>"
            for name, state in sorted(services.items())
        )
        + "</div>"
        "<div class='section-title' style='margin-top:18px'><h2>Reconcile state</h2></div>"
        f"<ul>{''.join(reconcile_rows)}</ul>"
        "</aside>"
        "</div>"
        "<div class='grid'>"
        "<section class='card'><div class='section-title'><h2>Recent runtime reports</h2><a href='/runtime/reports'>open all</a></div>"
        f"<ul>{''.join(report_items)}</ul></section>"
        "<div class='stack'>"
        "<section class='card'><div class='section-title'><h2>Recent exports</h2><a href='/v1/exports'>manifest</a></div>"
        f"<ul>{''.join(export_items)}</ul></section>"
        "<section class='card'><div class='section-title'><h2>Useful endpoints</h2></div>"
        f"<ul>{endpoint_rows}</ul></section>"
        "</div></div></div></body></html>"
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
            if path in {"/", "/settings"}:
                return True
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
            secure = (
                True
                if auth_config.cookie_secure_mode == "always"
                else False
                if auth_config.cookie_secure_mode == "never"
                else _request_is_secure(self, export_base_urls=export_base_urls)
            )
            _set_cookie_headers(
                self,
                key=auth_config.cookie_name,
                value=session_token,
                max_age=auth_config.session_days * 24 * 60 * 60,
                secure=secure,
            )

        def _clear_frontend_auth_cookie(self) -> None:
            secure = (
                True
                if auth_config.cookie_secure_mode == "always"
                else False
                if auth_config.cookie_secure_mode == "never"
                else _request_is_secure(self, export_base_urls=export_base_urls)
            )
            _set_cookie_headers(
                self,
                key=auth_config.cookie_name,
                value="",
                max_age=0,
                secure=secure,
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

            if path == "/auth/sessions":
                current_auth = self._frontend_auth_session()
                if not current_auth.authenticated:
                    _error_response(self, 401, "AUTH_REQUIRED", "Authentication required")
                    return
                conn = service.connect()
                try:
                    sessions = service.list_frontend_auth_sessions(conn, auth_session=current_auth)
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="auth.sessions.list")
                    return
                _json_response(self, 200, {"ok": True, "sessions": sessions})
                return

            if path == "/login":
                next_path = str(query.get("next", ["/"])[0] or "/")
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
                next_path = str(query.get("next", ["/"])[0] or "/")
                error = str(query.get("error", [""])[0] or "").strip() or None
                if auth_session.authenticated:
                    _redirect_response(self, next_path)
                    return
                if not auth_config.enabled or not auth_config.allow_registration:
                    _error_response(self, 403, "REGISTRATION_DISABLED", "Registration is disabled")
                    return
                _html_response(
                    self,
                    200,
                    _frontend_register_html(
                        next_path=next_path,
                        error=error,
                        registration_allowlist=list(auth_config.registration_allowlist),
                    ),
                )
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

            if path == "/":
                payload = service.landing_page_data()
                _html_response(
                    self,
                    200,
                    _landing_page_html(
                        auth_session=auth_session,
                        runtime_status=payload.runtime_status,
                        latest_report=payload.latest_report,
                        reports=payload.reports,
                        exports=payload.exports,
                    ),
                )
                return

            if path == "/settings":
                conn = service.connect()
                auth_status = service.frontend_auth_status(conn)
                sessions = service.list_frontend_auth_sessions(conn, auth_session=auth_session)
                _html_response(
                    self,
                    200,
                    _frontend_settings_html(
                        auth_session=auth_session,
                        auth_status=auth_status,
                        sessions=sessions,
                    ),
                )
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

            if path in {"/auth/register", "/auth/login", "/auth/logout"} or re.fullmatch(r"/auth/sessions/\d+/revoke", path):
                csrf_error = _validate_same_origin_post(self, export_base_urls=export_base_urls)
                if csrf_error:
                    _error_response(self, 403, "CSRF_FAILED", csrf_error)
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

            m = re.fullmatch(r"/auth/sessions/(\d+)/revoke", path)
            if m:
                current_auth = self._frontend_auth_session()
                if not current_auth.authenticated:
                    _error_response(self, 401, "AUTH_REQUIRED", "Authentication required")
                    return
                conn = service.connect()
                session_id = int(m.group(1))
                try:
                    revoked = service.revoke_frontend_auth_session(
                        conn,
                        auth_session=current_auth,
                        session_id=session_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="auth.sessions.revoke")
                    return
                if not revoked:
                    _error_response(self, 404, "NOT_FOUND", f"Auth session not found: {session_id}")
                    return
                data = json.dumps({"ok": True, "revoked": True, "session_id": session_id}, indent=2).encode("utf-8")
                self.send_response(200)
                if current_auth.session_id == session_id:
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
