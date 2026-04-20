from __future__ import annotations

import json
import mimetypes
import re
import subprocess
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse

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


_BROWSER_ESCAPE_HTML_JS = (
    "function escapeHtml(value){return String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('\\\"','&quot;').replaceAll(\"'\",'&#39;');}"
)

_BROWSER_BUSY_LABEL_JS = (
    "function rememberButtonLabel(button){if(button&&button.dataset.labelDefault===undefined)button.dataset.labelDefault=button.textContent||'';}"
    "function setButtonBusyLabel(button,isBusy,busyLabel){if(!button)return;rememberButtonLabel(button);button.textContent=isBusy?busyLabel:(button.dataset.labelDefault||button.textContent||'');}"
)

_BROWSER_FETCH_JSON_HELPERS_JS = (
    "async function fetchJsonResponse(input,init){const resp=await fetch(input,init);const data=await resp.json().catch(()=>null);return {resp,data};}"
    "function responseErrorMessage(data,fallback){return data?.error?.message||fallback;}"
)

_BROWSER_DIALOG_CSS = (
    ".browser-dialog{border:none;border-radius:22px;padding:0;width:min(100%,520px);background:#fffdf9;color:var(--ink, #122033);box-shadow:0 24px 60px rgba(18,32,51,.18)}"
    ".browser-dialog::backdrop{background:rgba(18,32,51,.45)}"
    ".browser-dialog-form{padding:22px;display:grid;gap:14px}"
    ".browser-dialog-head{display:flex;align-items:start;justify-content:space-between;gap:12px}"
    ".browser-dialog-title{margin:0;font-size:22px;line-height:1.15}"
    ".browser-dialog-close{margin:0;border:none;background:transparent;color:var(--muted, #5f6c7b);font-size:24px;line-height:1;cursor:pointer;padding:0 2px}"
    ".browser-dialog-message{margin:0;color:var(--muted, #5f6c7b);line-height:1.5}"
    ".browser-dialog-field{display:grid;gap:6px}"
    ".browser-dialog-field input{width:100%;padding:11px 12px;border:1px solid var(--line, #d9d0c3);border-radius:12px;background:#fffdf9;color:inherit}"
    ".browser-dialog-checkbox{display:flex;align-items:start;gap:10px;font-size:14px;color:var(--ink, #122033)}"
    ".browser-dialog-checkbox input{margin-top:2px;width:16px;height:16px}"
    ".browser-dialog-actions{display:flex;justify-content:flex-end;gap:10px;padding:0;margin:0}"
    ".browser-dialog-actions button{margin-top:0}"
    ".browser-dialog-confirm-danger{border-color:#efb5b5!important;background:#fff1f1!important;color:#a12828!important}"
)

_BROWSER_DIALOG_JS = (
    "let browserDialogState=null;"
    "function ensureBrowserDialog(){let dialog=document.getElementById('browser-action-dialog');if(dialog)return dialog;dialog=document.createElement('dialog');dialog.id='browser-action-dialog';dialog.className='browser-dialog';dialog.innerHTML=`<form method=\"dialog\" class=\"browser-dialog-form\"><div class=\"browser-dialog-head\"><h2 class=\"browser-dialog-title\" id=\"browser-dialog-title\">Confirm action</h2><button type=\"button\" class=\"browser-dialog-close\" id=\"browser-dialog-close\" aria-label=\"Close dialog\">&times;</button></div><p class=\"browser-dialog-message\" id=\"browser-dialog-message\"></p><label class=\"browser-dialog-field\" id=\"browser-dialog-input-wrap\" hidden><span id=\"browser-dialog-input-label\"></span><input id=\"browser-dialog-input\" autocomplete=\"off\" /></label><label class=\"browser-dialog-checkbox\" id=\"browser-dialog-checkbox-wrap\" hidden><input type=\"checkbox\" id=\"browser-dialog-checkbox\" /><span id=\"browser-dialog-checkbox-label\"></span></label><div class=\"hint bad\" id=\"browser-dialog-error\" hidden></div><div class=\"browser-dialog-actions\"><button type=\"button\" id=\"browser-dialog-cancel\">Cancel</button><button type=\"button\" id=\"browser-dialog-confirm\">Confirm</button></div></form>`;document.body.append(dialog);const closeButton=dialog.querySelector('#browser-dialog-close');const cancelButton=dialog.querySelector('#browser-dialog-cancel');const confirmButton=dialog.querySelector('#browser-dialog-confirm');function finish(result){const state=browserDialogState;browserDialogState=null;if(dialog.open)dialog.close();if(state?.resolve)state.resolve(result);}closeButton.addEventListener('click',()=>finish({confirmed:false,value:'',checked:false}));cancelButton.addEventListener('click',()=>finish({confirmed:false,value:'',checked:false}));dialog.addEventListener('cancel',(event)=>{event.preventDefault();finish({confirmed:false,value:'',checked:false});});confirmButton.addEventListener('click',()=>{const input=dialog.querySelector('#browser-dialog-input');const checkbox=dialog.querySelector('#browser-dialog-checkbox');const error=dialog.querySelector('#browser-dialog-error');const state=browserDialogState;if(!state)return;const value=(input.value||'').trim();const checked=!!checkbox.checked;if(state.requiredText&&value!==state.requiredText){error.textContent=state.requiredTextError||`Type ${state.requiredText} to continue.`;error.hidden=false;input.focus();input.select();return;}error.textContent='';error.hidden=true;finish({confirmed:true,value,checked});});return dialog;}"
    "async function requestBrowserDialog(options){const dialog=ensureBrowserDialog();const title=dialog.querySelector('#browser-dialog-title');const message=dialog.querySelector('#browser-dialog-message');const inputWrap=dialog.querySelector('#browser-dialog-input-wrap');const inputLabel=dialog.querySelector('#browser-dialog-input-label');const input=dialog.querySelector('#browser-dialog-input');const checkboxWrap=dialog.querySelector('#browser-dialog-checkbox-wrap');const checkbox=dialog.querySelector('#browser-dialog-checkbox');const checkboxLabel=dialog.querySelector('#browser-dialog-checkbox-label');const error=dialog.querySelector('#browser-dialog-error');const confirmButton=dialog.querySelector('#browser-dialog-confirm');const cancelButton=dialog.querySelector('#browser-dialog-cancel');title.textContent=String(options?.title||'Confirm action');message.textContent=String(options?.message||'');inputWrap.hidden=!options?.inputLabel;inputLabel.textContent=String(options?.inputLabel||'');input.value='';input.placeholder=String(options?.inputPlaceholder||'');checkboxWrap.hidden=!options?.checkboxLabel;checkbox.checked=false;checkboxLabel.textContent=String(options?.checkboxLabel||'');error.textContent='';error.hidden=true;confirmButton.textContent=String(options?.confirmLabel||'Confirm');cancelButton.textContent=String(options?.cancelLabel||'Cancel');confirmButton.classList.toggle('browser-dialog-confirm-danger',!!options?.danger);browserDialogState={resolve:null,requiredText:options?.requiredText||'',requiredTextError:options?.requiredTextError||''};const result=await new Promise((resolve)=>{browserDialogState.resolve=resolve;if(typeof dialog.showModal==='function'){dialog.showModal();}else{dialog.setAttribute('open','open');}window.requestAnimationFrame(()=>{if(!inputWrap.hidden){input.focus();return;}confirmButton.focus();});});confirmButton.classList.remove('browser-dialog-confirm-danger');return result;}"
)

_INLINE_MANAGER_JS = (
    "function setInlineManagerBusyState(current,config,isBusy){for(const attr of [config.renameToggleAttr,config.renameCancelAttr,config.renameSaveAttr,config.deleteAttr]){for(const el of document.querySelectorAll(`[${attr}=\\\"${CSS.escape(current)}\\\"]`)){if('disabled' in el)el.disabled=isBusy;el.dataset.busy=isBusy?'true':'false';if(attr===config.renameSaveAttr)setButtonBusyLabel(el,isBusy,'saving…');if(attr===config.deleteAttr)setButtonBusyLabel(el,isBusy,'deleting…');}}const input=document.getElementById(`${config.renameInputPrefix}${current}`);if(input)input.disabled=isBusy;}"
    "function setInlineManagerRowError(current,config,message){const errorRow=document.getElementById(`${config.rowErrorPrefix}${current}`);if(!errorRow)return;if(message){errorRow.textContent=message;errorRow.hidden=false;return;}errorRow.textContent='';errorRow.hidden=true;}"
    "function setInlineManagerRowOutcome(current,config,message,isError){const state=document.getElementById(`${config.rowStatePrefix}${current}`);if(!state)return;if(!message){state.textContent='';state.className='inline-state';return;}state.textContent=message;state.className=`inline-state show ${isError?'bad':'ok'}`;}"
    "function bindInlineManagerActions(scope,config){for(const button of scope.querySelectorAll(`[${config.renameToggleAttr}]`)){if(button.dataset.bound==='true')continue;button.dataset.bound='true';button.addEventListener('click',()=>{if(button.dataset.busy==='true')return;const current=button.getAttribute(config.renameToggleAttr);if(!current)return;setInlineManagerRowError(current,config,'');setInlineManagerRowOutcome(current,config,'',false);const row=document.getElementById(`${config.renameRowPrefix}${current}`);if(row)row.hidden=false;const input=document.getElementById(`${config.renameInputPrefix}${current}`);if(input){input.focus();input.select();}});}for(const button of scope.querySelectorAll(`[${config.renameCancelAttr}]`)){if(button.dataset.bound==='true')continue;button.dataset.bound='true';button.addEventListener('click',()=>{if(button.dataset.busy==='true')return;const current=button.getAttribute(config.renameCancelAttr);if(!current)return;setInlineManagerRowError(current,config,'');setInlineManagerRowOutcome(current,config,'',false);const row=document.getElementById(`${config.renameRowPrefix}${current}`);if(row)row.hidden=true;const input=document.getElementById(`${config.renameInputPrefix}${current}`);if(input)input.value=current;});}for(const button of scope.querySelectorAll(`[${config.renameSaveAttr}]`)){if(button.dataset.bound==='true')continue;button.dataset.bound='true';button.addEventListener('click',async()=>{if(button.dataset.busy==='true')return;const current=button.getAttribute(config.renameSaveAttr);if(!current)return;const input=document.getElementById(`${config.renameInputPrefix}${current}`);const next=(input?.value||'').trim();if(!next||next===current){setInlineManagerRowError(current,config,'');setInlineManagerRowOutcome(current,config,'',false);const row=document.getElementById(`${config.renameRowPrefix}${current}`);if(row)row.hidden=true;return;}setInlineManagerRowError(current,config,'');setInlineManagerRowOutcome(current,config,'',false);setInlineManagerBusyState(current,config,true);try{const {resp,data}=await fetchJsonResponse(config.renamePath(current,next),{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(config.renameBody(next))});if(resp.ok){config.applyRename(current,next);setInlineManagerRowOutcome(next,config,'saved',false);config.setFeedback(`Renamed ${config.itemLabel} ${current} to ${next}.`,false);return;}const message=responseErrorMessage(data,'Rename failed');setInlineManagerRowError(current,config,message);setInlineManagerRowOutcome(current,config,'error',true);config.setFeedback(message,true);}finally{setInlineManagerBusyState(current,config,false);}});}for(const button of scope.querySelectorAll(`[${config.deleteAttr}]`)){if(button.dataset.bound==='true')continue;button.dataset.bound='true';button.addEventListener('click',async()=>{if(button.dataset.busy==='true')return;const current=button.getAttribute(config.deleteAttr);if(!current)return;setInlineManagerRowError(current,config,'');setInlineManagerRowOutcome(current,config,'',false);const decision=await requestBrowserDialog({title:`Delete ${config.itemLabel}`,message:config.deleteConfirm(current),confirmLabel:'Delete',cancelLabel:'Cancel',danger:true});if(!decision.confirmed)return;setInlineManagerBusyState(current,config,true);try{const {resp,data}=await fetchJsonResponse(config.deletePath(current),{method:'DELETE'});if(resp.ok){config.removeRow(current);config.setFeedback(`Deleted ${config.itemLabel} ${current}.`,false);return;}const message=responseErrorMessage(data,'Delete failed');setInlineManagerRowError(current,config,message);setInlineManagerRowOutcome(current,config,'error',true);config.setFeedback(message,true);}finally{setInlineManagerBusyState(current,config,false);}});}}"
)


def _login_path(*, next_path: str = "/", reason: str | None = None, error: str | None = None) -> str:
    params: dict[str, str] = {"next": next_path}
    if reason:
        params["reason"] = reason
    if error:
        params["error"] = error
    return f"/login?{urlencode(params)}"


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


def _requires_same_origin_write(path: str) -> bool:
    if path in {"/auth/register", "/auth/login", "/auth/logout"}:
        return True
    if re.fullmatch(r"/auth/sessions/\d+/revoke", path):
        return True
    if path == "/v1/runtime/reports":
        return True
    if re.fullmatch(r"/v1/runtime/reports/[^/]+/rename", path):
        return True
    if re.fullmatch(r"/v1/runtime/reports/[^/]+", path):
        return True
    if path == "/v1/exports":
        return True
    if re.fullmatch(r"/v1/exports/[^/]+/rename", path):
        return True
    if re.fullmatch(r"/v1/exports/[^/]+", path):
        return True
    if path == "/v1/tenants/onboard":
        return True
    if re.fullmatch(r"/v1/tenants/[^/]+/credentials", path):
        return True
    if re.fullmatch(r"/v1/tenants/[^/]+/activate", path):
        return True
    if re.fullmatch(r"/v1/tenants/[^/]+/(live|backfill|retire)", path):
        return True
    return False


def _frontend_login_html(*, next_path: str, error: str | None = None, reason: str | None = None, can_register: bool) -> str:
    error_html = ""
    if error:
        error_html = f"<p class='error'>{escape(error)}</p>"
    banner_html = ""
    if reason == "auth_required":
        banner_html = "<p class='banner banner-info'>Sign in to continue to the protected page you requested.</p>"
    elif reason == "signed_out":
        banner_html = "<p class='banner banner-info'>You have been signed out.</p>"
    elif reason == "session_revoked":
        banner_html = "<p class='banner banner-info'>Your current session was revoked. Sign in again to continue.</p>"
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
        ".banner{padding:10px 12px;border-radius:10px;margin:14px 0}"
        ".banner-info{color:#0b57d0;background:#eff6ff;border:1px solid #bfdbfe}"
        ".meta{margin-top:14px;color:#475569;font-size:14px}"
        "code{background:#e2e8f0;padding:1px 5px;border-radius:6px}"
        "</style></head><body>"
        "<div class='card'>"
        "<h1>Slack Mirror</h1>"
        "<p>Sign in to access published exports and runtime reports.</p>"
        "<p class='meta'>Browser sign-in stays persistent across restarts until the configured session lifetime or idle timeout expires.</p>"
        f"{banner_html}"
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
        "<p class='meta'>Password reset: run <code>slack-mirror-user user-env provision-frontend-user --username &lt;your-username&gt; --password-env &lt;ENV_VAR&gt; --reset-password</code>.</p>"
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


def _authenticated_topbar_css() -> str:
    return (
        ".auth-topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;"
        "margin-bottom:18px;padding:14px 16px;border:1px solid var(--line);border-radius:18px;background:rgba(255,253,249,.88);box-shadow:var(--shadow)}"
        ".auth-identity{color:var(--muted);font-size:13px;line-height:1.45}"
        ".auth-nav{display:flex;flex-wrap:wrap;gap:10px}"
        ".nav-link{display:inline-flex;align-items:center;gap:8px;padding:10px 12px;border-radius:14px;border:1px solid var(--line);background:#f8f5ef;color:var(--ink);font-weight:700}"
        ".nav-link.active{background:#edf4ff;border-color:#b7c9ee;color:var(--accent)}"
        ".nav-link.logout{background:#fff1f2;border-color:#fecdd3;color:#be123c}"
    )


def _authenticated_topbar_html(*, auth_session: FrontendAuthSession, current_path: str) -> str:
    if auth_session.authenticated:
        user_label = auth_session.display_name or auth_session.username or "Authenticated user"
        identity_html = (
            f"Signed in as <strong>{escape(user_label)}</strong> · username <code>{escape(str(auth_session.username or ''))}</code>"
        )
    else:
        user_label = "Local access"
        identity_html = "Local browser access is enabled for this install."
    nav_items = [
        ("/", "Home", False),
        ("/search", "Search", False),
        ("/logs", "Logs", False),
        ("/runtime/reports", "Runtime reports", False),
        ("/exports", "Exports", False),
        ("/settings/tenants", "Tenants", False),
        ("/settings", "Settings", False),
        ("/logout", "Logout", True),
    ]
    links = []
    for href, label, is_logout in nav_items:
        classes = ["nav-link"]
        if current_path == href:
            classes.append("active")
        if is_logout:
            classes.append("logout")
        links.append(f"<a class='{' '.join(classes)}' href=\"{href}\">{escape(label)}</a>")
    return (
        "<div class='auth-topbar'>"
        f"<div class='auth-identity'>{identity_html}</div>"
        f"<nav class='auth-nav'>{''.join(links)}</nav>"
        "</div>"
    )


def _tenant_settings_html(*, auth_session: FrontendAuthSession, tenants: list[dict[str, Any]]) -> str:
    tenants_json = json.dumps(tenants)

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Slack Mirror Tenants</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<style>"
        ":root{--bg:#f4efe7;--panel:#fffdf9;--ink:#122033;--muted:#5f6c7b;--line:#d9d0c3;--accent:#0b57d0;--bad:#a12828;--bad-soft:#fde5e5;--ok:#1f7a44;--ok-soft:#ddefe3;--warn:#a05a00;--warn-soft:#fff0db;--shadow:0 14px 30px rgba(18,32,51,.08);}"
        "*{box-sizing:border-box}body{margin:0;font-family:\"Aptos\",\"Segoe UI\",Arial,sans-serif;background:linear-gradient(180deg,#f6f1e9 0,#efe7dc 100%);color:var(--ink)}"
        f"{_authenticated_topbar_css()}"
        ".shell{max-width:1120px;margin:0 auto;padding:28px 18px 40px}.top{margin-bottom:18px}.eyebrow{display:inline-block;padding:6px 10px;border-radius:999px;background:#ebe4d8;color:#514739;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase}"
        "h1{margin:8px 0;font-size:34px}h2{margin:0;font-size:20px}.meta{color:var(--muted);font-size:13px;line-height:1.45}code{background:#efe7da;border:1px solid #dfd3c2;padding:2px 6px;border-radius:8px;font-size:12px}"
        ".layout{display:grid;grid-template-columns:1fr 1fr;gap:18px}.layout-full{grid-column:1 / -1}.card,.tenant-card{background:var(--panel);border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:22px}.stack{display:grid;gap:14px}.tenant-head{display:flex;justify-content:space-between;gap:12px;align-items:center}.tenant-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:14px}.tenant-card .button-row{margin-top:14px}"
        ".badge{display:inline-flex;align-items:center;padding:4px 9px;border-radius:999px;font-size:12px;font-weight:700;line-height:1}.badge-ok{background:var(--ok-soft);color:var(--ok)}.badge-warn{background:var(--warn-soft);color:var(--warn)}.badge-bad{background:var(--bad-soft);color:var(--bad)}.badge-neutral{background:#ebe4d8;color:#514739}"
        ".status-block{padding:12px 14px;border:1px solid #e6ddd2;border-radius:16px;background:#fcfaf6}.status-block strong{display:block;margin-bottom:6px}.status-strip{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 0}.status-pill{display:inline-flex;align-items:center;padding:5px 9px;border-radius:999px;font-size:12px;font-weight:700}.status-pill.ok{background:var(--ok-soft);color:var(--ok)}.status-pill.warn{background:var(--warn-soft);color:var(--warn)}.status-pill.bad{background:var(--bad-soft);color:var(--bad)}.status-pill.neutral{background:#ebe4d8;color:#514739}"
        "label{display:block;margin:12px 0 6px;font-weight:700}input{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:12px;background:#fffdf9;color:var(--ink)}button{margin-top:14px;padding:11px 14px;border-radius:14px;border:1px solid #b7c9ee;background:#edf4ff;color:var(--accent);font-weight:700;cursor:pointer}.button-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}.button-row button{margin-top:0}.danger{border-color:#efb5b5;background:#fff1f1;color:var(--bad)}.hint{margin-top:8px;color:var(--muted);font-size:13px}.empty{padding:16px;border:1px dashed #d6cbbb;border-radius:16px;color:var(--muted);background:#fbf7f0}"
        ".collapsible-card{padding:0;overflow:hidden}.collapsible-summary{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;list-style:none;cursor:pointer;padding:22px}.collapsible-summary::-webkit-details-marker{display:none}.collapsible-copy{min-width:0}.collapsible-summary h2{margin:0 0 6px}.collapsible-chevron{flex:0 0 auto;color:var(--muted);font-size:20px;line-height:1;transform:rotate(0deg);transition:transform .18s ease}.collapsible-card[open] .collapsible-chevron{transform:rotate(90deg)}.collapsible-body{padding:0 22px 22px;border-top:1px solid #efe5d8}"
        "#tenant-feedback{display:none;margin-top:12px;padding:12px 14px;border-radius:14px}.feedback-ok{display:block!important;background:var(--ok-soft);color:var(--ok)}.feedback-bad{display:block!important;background:var(--bad-soft);color:var(--bad)}.tenant-inline-feedback{margin-top:14px}"
        f"{_BROWSER_DIALOG_CSS}"
        "@media (max-width: 860px){.layout,.tenant-grid{grid-template-columns:1fr}}"
        "</style></head><body><div class='shell'>"
        f"{_authenticated_topbar_html(auth_session=auth_session, current_path='/settings/tenants')}"
        "<div class='top'><span class='eyebrow'>Settings</span><h1>Tenant onboarding</h1>"
        "<div class='meta'>Manage Slack Mirror tenants from the same config-backed workflow used by the CLI. Secret values are never displayed here.</div></div>"
        "<div class='layout'>"
        "<details class='card collapsible-card' id='tenant-onboard-panel' open><summary class='collapsible-summary'><div class='collapsible-copy'><h2>Add tenant scaffold</h2>"
        "<div class='meta'>This creates a disabled workspace block, renders a JSON Slack app manifest, syncs the DB, and stops at the credential checkpoint.</div></div><span class='collapsible-chevron' aria-hidden='true'>&rsaquo;</span></summary><div class='collapsible-body'>"
        "<form id='tenant-onboard-form'>"
        "<label for='tenant-name'>Tenant name</label><input id='tenant-name' name='name' placeholder='polymer' required>"
        "<label for='tenant-domain'>Slack domain or URL</label><input id='tenant-domain' name='domain' placeholder='https://example.slack.com' required>"
        "<label for='tenant-display-name'>Display name</label><input id='tenant-display-name' name='display_name' placeholder='Example Company'>"
        "<button id='tenant-onboard-button' type='submit'>Create disabled scaffold</button>"
        "<div class='hint'>After scaffold creation, use the JSON manifest in Slack, then store the listed env vars in the configured dotenv file.</div>"
        "<div id='tenant-feedback'></div>"
        "</form></div></details>"
        "<details class='card collapsible-card' id='tenant-credentials-panel'><summary class='collapsible-summary'><div class='collapsible-copy'><h2>Install credentials</h2>"
        "<div class='meta'>Paste credentials only on this local settings page. Values are written to the configured dotenv and are never rendered back.</div></div><span class='collapsible-chevron' aria-hidden='true'>&rsaquo;</span></summary><div class='collapsible-body'>"
        "<form id='tenant-credentials-form'>"
        "<label for='credential-tenant-name'>Tenant name</label><input id='credential-tenant-name' name='name' placeholder='polymer' required>"
        "<label for='credential-bot-token'>Bot token</label><input id='credential-bot-token' name='token' type='password' placeholder='xoxb-...' autocomplete='new-password'>"
        "<label for='credential-write-bot-token'>Write bot token</label><input id='credential-write-bot-token' name='outbound_token' type='password' placeholder='xoxb-...' autocomplete='new-password'>"
        "<label for='credential-app-token'>Socket Mode app token</label><input id='credential-app-token' name='app_token' type='password' placeholder='xapp-...' autocomplete='new-password'>"
        "<label for='credential-signing-secret'>Signing secret</label><input id='credential-signing-secret' name='signing_secret' type='password' placeholder='secret' autocomplete='new-password'>"
        "<label for='credential-team-id'>Team ID</label><input id='credential-team-id' name='team_id' placeholder='T...' autocomplete='off'>"
        "<label for='credential-user-token'>User token</label><input id='credential-user-token' name='user_token' type='password' placeholder='xoxp-...' autocomplete='new-password'>"
        "<label for='credential-write-user-token'>Write user token</label><input id='credential-write-user-token' name='outbound_user_token' type='password' placeholder='xoxp-...' autocomplete='new-password'>"
        "<button id='tenant-credentials-button' type='submit'>Install credentials</button>"
        "<div class='hint'>Leave optional fields blank. Use write-token fields only when write actions are intentionally enabled.</div>"
        "</form></div></details>"
        "<section class='stack layout-full' id='tenant-list'></section>"
        "</div>"
        "<script>"
        f"const initialTenants={tenants_json};"
        "const pendingTenantActions=new Map();"
        "const tenantActionFeedback=new Map();"
        "let tenantPollHandle=null;"
        "let tenantPollRemaining=0;"
        "const tenantList=document.getElementById('tenant-list');"
        "const form=document.getElementById('tenant-onboard-form');const onboardingFeedback=document.getElementById('tenant-feedback');const button=document.getElementById('tenant-onboard-button');"
        "const credentialsForm=document.getElementById('tenant-credentials-form');const credentialsButton=document.getElementById('tenant-credentials-button');"
        "function showOnboardingFeedback(message,isError){onboardingFeedback.textContent=message;onboardingFeedback.className=isError?'feedback-bad':'feedback-ok';}"
        f"{_BROWSER_ESCAPE_HTML_JS}"
        f"{_BROWSER_DIALOG_JS}"
        "function badgeClass(tone){if(tone==='ok')return 'badge-ok';if(tone==='bad')return 'badge-bad';if(tone==='neutral')return 'badge-neutral';return 'badge-warn';}"
        "function pillClass(tone){if(tone==='ok')return 'status-pill ok';if(tone==='bad')return 'status-pill bad';if(tone==='neutral')return 'status-pill neutral';return 'status-pill warn';}"
        "function setTenantPendingAction(name,action){pendingTenantActions.set(String(name),String(action));}"
        "function clearTenantPendingAction(name){pendingTenantActions.delete(String(name));}"
        "function setTenantActionFeedback(name,message,isError){tenantActionFeedback.set(String(name),{message:String(message||''),isError:!!isError});}"
        "function clearTenantActionFeedback(name){tenantActionFeedback.delete(String(name));}"
        "function startTenantPolling(cycles=6,delay=1500){tenantPollRemaining=Math.max(tenantPollRemaining,cycles);if(tenantPollHandle)return;tenantPollHandle=window.setInterval(async()=>{if(tenantPollRemaining<=0){window.clearInterval(tenantPollHandle);tenantPollHandle=null;return;}tenantPollRemaining-=1;try{await refreshTenants();}catch(error){}} ,delay);}"
        "function tenantCardHtml(item){const name=String(item.name||'unknown');const domain=String(item.domain||'');const enabled=!!item.enabled;const credentialReady=!!item.credential_ready;const synced=!!item.db_synced;const missing=(item.missing_required_credentials||[]).join(', ')||'-';const manifest=item.manifest||{};const nextAction=String(item.next_action||'unknown');const health=item.health||{};const syncHealth=item.sync_health||{};const backfillStatus=item.backfill_status||{};const dbStats=item.db_stats||{};const liveUnits=item.live_units||{};const validationStatus=String(item.validation_status||'unknown');const pendingAction=pendingTenantActions.get(name)||'';const feedbackState=tenantActionFeedback.get(name)||null;const webhooksState=String(liveUnits.webhooks||'unknown');const daemonState=String(liveUnits.daemon||'unknown');const healthTone=String(health.tone||'neutral');const syncTone=String(syncHealth.tone||'neutral');const backfillTone=String(backfillStatus.tone||'neutral');const unitsActive=webhooksState==='active'||daemonState==='active';const canActivate=!pendingAction&&nextAction==='ready_to_activate';const canStartLive=!pendingAction&&nextAction==='start_live_sync';const canRunInitialSync=!pendingAction&&nextAction==='run_initial_sync';const canRestartLive=!pendingAction&&enabled&&unitsActive&&validationStatus!=='healthy';const canStopLive=!pendingAction&&enabled&&unitsActive;const manifestButton=`<button data-tenant-copy-manifest=\"${name}\">Copy Manifest JSON</button><div class='hint'>Slack only accepts pasted manifest JSON. This copies the rendered manifest to your clipboard.</div>`;const dbSummary=`${Number(dbStats.channels||0)} channels · ${Number(dbStats.messages||0)} messages · ${Number(dbStats.files||0)} files`;const dbDetail=`attachment text ${Number(dbStats.attachment_text||0)} · OCR ${Number(dbStats.ocr_text||0)} · embedding pending ${Number(dbStats.embedding_pending||0)} · derived pending ${Number(dbStats.derived_pending||0)}`;const feedbackHtml=feedbackState&&feedbackState.message?`<div class='${feedbackState.isError?'feedback-bad':'feedback-ok'} tenant-inline-feedback'>${escapeHtml(feedbackState.message)}</div>`:'';let actionRows='';if(canActivate){actionRows+=`<div class='button-row'><button data-tenant-activate=\"${name}\">Activate tenant</button></div><div class='hint'>This enables the tenant, installs live sync, and starts an initial bounded history sync.</div>`;}else if(canStartLive){actionRows+=`<div class='button-row'><button data-tenant-live=\"${name}\" data-live-action='start'>Start live sync</button></div><div class='hint'>Live sync is stopped. Start it to resume steady-state ingest.</div>`;}else if(canRunInitialSync){actionRows+=`<div class='button-row'><button data-tenant-backfill=\"${name}\">Run initial sync</button></div><div class='hint'>Live sync is active, but the tenant has not recorded an initial bounded history sync yet.</div>`;}else if(pendingAction==='activate'){actionRows+=`<div class='hint'>Activation is in progress. This tile will refresh as live sync and initial history sync settle.</div>`;}else if(!enabled){actionRows+=`<div class='hint'>Activation appears when credentials are ready and the tenant is synced into the DB.</div>`;}if(pendingAction==='start'||pendingAction==='restart'||pendingAction==='stop'){actionRows+=`<div class='hint'>Live sync action <code>${pendingAction}</code> is in progress. This tile is polling for the updated unit state.</div>`;}if(pendingAction==='backfill'){actionRows+=`<div class='hint'>Initial sync is in progress. This tile is polling for queue and DB-stat changes.</div>`;}const maintenanceButtons=[];if(canRestartLive)maintenanceButtons.push(`<button data-tenant-live=\"${name}\" data-live-action='restart'>Restart live sync</button>`);if(canStopLive)maintenanceButtons.push(`<button data-tenant-live=\"${name}\" data-live-action='stop'>Stop live sync</button>`);if(nextAction!=='run_initial_sync'&&!pendingAction&&enabled&&synced&&String(backfillStatus.label||'')!=='syncing'&&String(backfillStatus.label||'')!=='needs_initial_sync')maintenanceButtons.push(`<button data-tenant-backfill=\"${name}\">Run bounded backfill</button>`);if(maintenanceButtons.length)actionRows+=`<div class='hint'>Maintenance</div><div class='button-row'>${maintenanceButtons.join('')}</div>`;actionRows+=`<div class='button-row'><button class='danger' title='Retire tenant' data-tenant-retire=\"${name}\">&#128465; Retire tenant</button></div>`;return `<article class='tenant-card tenant-card-full' data-tenant-card=\"${name}\"><div class='tenant-head'><h2>${name}</h2><span class='badge ${badgeClass(enabled?'ok':'warn')}'>${enabled?'enabled':'disabled'}</span></div><div class='meta'>Slack domain <code>${domain}</code></div>${feedbackHtml}<div class='tenant-grid'><div class='status-block'><strong>Credentials</strong><div class='meta'>${credentialReady?'ready':'missing'} · missing <code>${missing}</code></div><div class='status-strip'><span class='${pillClass(credentialReady?'ok':'warn')}'>${credentialReady?'ready':'needs credentials'}</span></div></div><div class='status-block'><strong>Mirrored DB</strong><div class='meta'>${dbSummary}</div><div class='hint'>${dbDetail}</div><div class='status-strip'><span class='status-pill neutral'>DB ${String(synced).toLowerCase()}</span><span class='status-pill neutral'>embedding errors ${Number(dbStats.embedding_errors||0)}</span><span class='status-pill neutral'>derived errors ${Number(dbStats.derived_errors||0)}</span></div></div><div class='status-block'><strong>History sync</strong><div class='meta'>${String(backfillStatus.summary||'No sync status available.')}</div><div class='hint'>${String(backfillStatus.detail||'')}</div><div class='status-strip'><span class='${pillClass(backfillTone)}'>${String(backfillStatus.label||'unknown')}</span></div></div><div class='status-block'><strong>Live sync</strong><div class='meta'>${String(syncHealth.summary||'No live-sync status available.')}</div><div class='hint'>${String(syncHealth.detail||'')}</div><div class='status-strip'><span class='${pillClass(syncTone)}'>${String(syncHealth.label||'unknown')}</span><span class='status-pill neutral'>webhooks ${webhooksState}</span><span class='status-pill neutral'>daemon ${daemonState}</span></div></div><div class='status-block'><strong>Health</strong><div class='meta'>${String(health.summary||'No health status available.')}</div><div class='hint'>${String(health.detail||'')}</div><div class='status-strip'><span class='${pillClass(healthTone)}'>${validationStatus}</span></div></div><div class='status-block'><strong>Recommended next step</strong><div class='meta'><code>${nextAction}</code></div></div><div class='status-block'><strong>Manifest</strong><div class='meta'>${manifestButton}<div class='hint'><code>${String(manifest.path||'')}</code></div></div></div></div>${actionRows}</article>`;}"
        "function bindTenantActions(){for(const manifestButton of document.querySelectorAll('button[data-tenant-copy-manifest]')){manifestButton.onclick=async()=>{const name=manifestButton.getAttribute('data-tenant-copy-manifest');const label=manifestButton.textContent;manifestButton.disabled=true;manifestButton.textContent='copying...';try{const resp=await fetch(`/v1/tenants/${encodeURIComponent(name)}/manifest`);const data=await resp.json().catch(()=>({error:{message:'Manifest copy failed'}}));if(!resp.ok){setTenantActionFeedback(name,data.error?.message||'Manifest copy failed',true);renderTenantList(window.latestTenants||initialTenants);return;}await navigator.clipboard.writeText(String(data.content||''));setTenantActionFeedback(name,`Copied manifest JSON for ${name}.`,false);renderTenantList(window.latestTenants||initialTenants);}catch(error){setTenantActionFeedback(name,'Clipboard write failed on this browser.',true);renderTenantList(window.latestTenants||initialTenants);}finally{manifestButton.disabled=false;manifestButton.textContent=label;}};}for(const activateButton of document.querySelectorAll('button[data-tenant-activate]')){activateButton.onclick=async()=>{const name=activateButton.getAttribute('data-tenant-activate');setTenantPendingAction(name,'activate');setTenantActionFeedback(name,'Activating tenant, installing live sync, and starting initial history sync...',false);renderTenantList(window.latestTenants||initialTenants);try{const resp=await fetch(`/v1/tenants/${encodeURIComponent(name)}/activate`,{method:'POST',headers:{'content-type':'application/json'},body:'{}'});const data=await resp.json().catch(()=>({error:{message:'Tenant activation failed'}}));if(!resp.ok){clearTenantPendingAction(name);setTenantActionFeedback(name,data.error?.message||'Tenant activation failed',true);await refreshTenants();return;}setTenantPendingAction(name,'backfill');renderTenantList(window.latestTenants||initialTenants);const backfillResp=await fetch(`/v1/tenants/${encodeURIComponent(name)}/backfill`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({auth_mode:'user',include_messages:true,include_files:false,channel_limit:10})});const backfillData=await backfillResp.json().catch(()=>({error:{message:'Initial sync failed'}}));if(!backfillResp.ok){clearTenantPendingAction(name);setTenantActionFeedback(name,backfillData.error?.message||'Initial sync failed after activation',true);await refreshTenants();return;}setTenantActionFeedback(name,`Activated ${data.tenant.name}. Initial history sync started and this tile will update automatically.`,false);await refreshTenants();startTenantPolling(10,2000);}catch(error){clearTenantPendingAction(name);setTenantActionFeedback(name,'Tenant activation failed',true);await refreshTenants();}};}for(const liveButton of document.querySelectorAll('button[data-tenant-live]')){liveButton.onclick=async()=>{const name=liveButton.getAttribute('data-tenant-live');const action=liveButton.getAttribute('data-live-action');setTenantPendingAction(name,action);setTenantActionFeedback(name,`Live action ${action} requested. Polling for updated status...`,false);renderTenantList(window.latestTenants||initialTenants);await refreshTenants();try{const resp=await fetch(`/v1/tenants/${encodeURIComponent(name)}/live`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({action})});const data=await resp.json().catch(()=>({error:{message:'Live action failed'}}));if(!resp.ok){clearTenantPendingAction(name);setTenantActionFeedback(name,data.error?.message||'Live action failed',true);await refreshTenants();return;}setTenantActionFeedback(name,`Live action ${data.action} completed for ${data.tenant.name}. Polling for updated status...`,false);await refreshTenants();startTenantPolling(6,1500);}catch(error){clearTenantPendingAction(name);setTenantActionFeedback(name,'Live action failed',true);await refreshTenants();}};}for(const backfillButton of document.querySelectorAll('button[data-tenant-backfill]')){backfillButton.onclick=async()=>{const name=backfillButton.getAttribute('data-tenant-backfill');setTenantPendingAction(name,'backfill');setTenantActionFeedback(name,'Initial history sync requested. Polling DB and queue stats...',false);renderTenantList(window.latestTenants||initialTenants);await refreshTenants();try{const resp=await fetch(`/v1/tenants/${encodeURIComponent(name)}/backfill`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({auth_mode:'user',include_messages:true,include_files:false,channel_limit:10})});const data=await resp.json().catch(()=>({error:{message:'Backfill failed'}}));if(!resp.ok){clearTenantPendingAction(name);setTenantActionFeedback(name,data.error?.message||'Backfill failed',true);await refreshTenants();return;}setTenantActionFeedback(name,`Initial history sync started for ${data.tenant.name}. Polling DB and queue stats...`,false);await refreshTenants();startTenantPolling(10,2000);}catch(error){clearTenantPendingAction(name);setTenantActionFeedback(name,'Backfill failed',true);await refreshTenants();}};}for(const retireButton of document.querySelectorAll('button[data-tenant-retire]')){retireButton.onclick=async()=>{const name=retireButton.getAttribute('data-tenant-retire');const decision=await requestBrowserDialog({title:`Retire tenant ${name}`,message:'This removes the tenant from config. Type the tenant name to confirm. Optionally also delete mirrored DB rows for the retired tenant.',inputLabel:'Confirm tenant name',inputPlaceholder:name,requiredText:name,requiredTextError:`Type ${name} to retire this tenant.`,checkboxLabel:'Also delete mirrored DB rows for this tenant',confirmLabel:'Retire tenant',cancelLabel:'Cancel',danger:true});if(!decision.confirmed)return;retireButton.disabled=true;retireButton.textContent='retiring...';try{const resp=await fetch(`/v1/tenants/${encodeURIComponent(name)}/retire`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({confirm:name,delete_db:decision.checked})});const data=await resp.json().catch(()=>({error:{message:'Retire failed'}}));if(!resp.ok){setTenantActionFeedback(name,data.error?.message||'Retire failed',true);renderTenantList(window.latestTenants||initialTenants);return;}clearTenantActionFeedback(name);showOnboardingFeedback(`Retired ${data.tenant.name}. DB deleted: ${data.db_deleted?'yes':'no'}.`,false);await refreshTenants();}finally{retireButton.disabled=false;retireButton.textContent='Retire tenant';}};}}"
        "function renderTenantList(tenants){window.latestTenants=tenants;if(!tenants.length){tenantList.innerHTML=\"<div class='empty'>No tenants are configured yet.</div>\";return;}tenantList.innerHTML=tenants.map(tenantCardHtml).join('');bindTenantActions();}"
        "async function refreshTenants(){const resp=await fetch('/v1/tenants');const data=await resp.json().catch(()=>({tenants:[]}));if(!resp.ok){throw new Error(data.error?.message||'Tenant refresh failed');}const tenants=data.tenants||[];for(const item of tenants){const name=String(item.name||'');const pending=pendingTenantActions.get(name)||'';if(!pending)continue;const units=item.live_units||{};const unitsActive=String(units.webhooks||'unknown')==='active'||String(units.daemon||'unknown')==='active';if(pending==='activate'&&!!item.enabled){clearTenantPendingAction(name);}else if((pending==='start'||pending==='restart')&&unitsActive){clearTenantPendingAction(name);}else if(pending==='stop'&&!unitsActive){clearTenantPendingAction(name);}else if(pending==='backfill'){const jobs=Number((item.db_stats||{}).embedding_pending||0)+Number((item.db_stats||{}).derived_pending||0);if(jobs===0&&String((item.backfill_status||{}).label||'')!=='syncing'){clearTenantPendingAction(name);}}}renderTenantList(tenants);}"
        "form.addEventListener('submit',async(event)=>{event.preventDefault();showOnboardingFeedback('',false);button.disabled=true;button.textContent='creating...';"
        "try{const payload={name:document.getElementById('tenant-name').value.trim(),domain:document.getElementById('tenant-domain').value.trim(),display_name:document.getElementById('tenant-display-name').value.trim()||undefined};"
        "const resp=await fetch('/v1/tenants/onboard',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});const data=await resp.json().catch(()=>({error:{message:'Tenant onboarding failed'}}));"
        "if(!resp.ok){showOnboardingFeedback(data.error?.message||'Tenant onboarding failed',true);return;}showOnboardingFeedback(`Created ${data.tenant.name}. Manifest ready to copy. Next: ${data.tenant.next_action}.`,false);await refreshTenants();}"
        "finally{button.disabled=false;button.textContent='Create disabled scaffold';}});"
        "credentialsForm.addEventListener('submit',async(event)=>{event.preventDefault();credentialsButton.disabled=true;credentialsButton.textContent='installing...';try{const name=document.getElementById('credential-tenant-name').value.trim();const credentials={};for(const id of ['team_id','token','outbound_token','user_token','outbound_user_token','app_token','signing_secret']){const node=document.querySelector(`#tenant-credentials-form [name=\"${id}\"]`);const value=(node?.value||'').trim();if(value)credentials[id]=value;}const resp=await fetch(`/v1/tenants/${encodeURIComponent(name)}/credentials`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({credentials})});const data=await resp.json().catch(()=>({error:{message:'Credential install failed'}}));if(!resp.ok){showOnboardingFeedback(data.error?.message||'Credential install failed',true);return;}showOnboardingFeedback(`Installed ${data.installed_keys.length} credential key(s). Readiness: ${data.tenant.credential_ready?'ready':'missing'}.`,false);credentialsForm.reset();await refreshTenants();}finally{credentialsButton.disabled=false;credentialsButton.textContent='Install credentials';}});"
        "renderTenantList(initialTenants);"
        "</script></div></body></html>"
    )


def _frontend_settings_html(
    *,
    auth_session: FrontendAuthSession,
    auth_status: dict[str, Any],
    sessions: list[dict[str, Any]],
) -> str:
    allowlist = auth_status.get("registration_allowlist") or []
    registration_policy = str(auth_status.get("registration_mode") or "closed")
    session_days = int(auth_status.get("session_days") or 0)
    session_idle_timeout_seconds = int(auth_status.get("session_idle_timeout_seconds") or 0)
    login_attempt_window_seconds = int(auth_status.get("login_attempt_window_seconds") or 0)
    login_attempt_max_failures = int(auth_status.get("login_attempt_max_failures") or 0)
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
        f"{_authenticated_topbar_css()}"
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
        f"{_authenticated_topbar_html(auth_session=auth_session, current_path='/settings')}"
        "<div class='top'>"
        "<div><span class='eyebrow'>Slack Mirror</span>"
        "<h1>Account settings</h1>"
        "<div class='meta'>Review browser-auth policy, current-user sessions, and revocation controls from one place.</div></div>"
        "</div>"
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
        "<h2>Auth governance</h2>"
        "<div class='meta'>Browser sessions stay signed in across browser restarts until the configured lifetime or idle timeout expires.</div>"
        "<ul>"
        f"<li class='list-row'><strong>Session lifetime</strong><div class='meta'><code>{session_days}</code> day(s)</div></li>"
        f"<li class='list-row'><strong>Idle timeout</strong><div class='meta'><code>{session_idle_timeout_seconds}</code> second(s)</div></li>"
        f"<li class='list-row'><strong>Login throttle</strong><div class='meta'><code>{login_attempt_max_failures}</code> failed attempt(s) per <code>{login_attempt_window_seconds}</code> second window</div></li>"
        "</ul>"
        "</section>"
        "<section class='card'>"
        "<h2>Password reset</h2>"
        "<div class='meta'>For now, password reset is a CLI-driven operator action.</div>"
        "<div class='list-row'><code>slack-mirror-user user-env provision-frontend-user --username &lt;your-username&gt; --password-env &lt;ENV_VAR&gt; --reset-password</code></div>"
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
        "if(resp.ok){markSessionInactive(sessionId,current);showFeedback(current?`Signed out session ${sessionId}. Redirecting to login...`:`Revoked session ${sessionId}.`,false);if(current){window.location.assign('/login?'+new URLSearchParams({next:'/',reason:'session_revoked'}));}return;}"
        "const data=await resp.json().catch(()=>({error:{message:'Revocation failed'}}));"
        "showFeedback(data.error?.message||'Revocation failed',true);button.disabled=false;});}"
        "</script>"
        "</div></body></html>"
    )

def _render_create_field_helper_js(*, manager_name: str, fields_js: str, descriptors_js: str) -> str:
    return "".join(
        [
            f"function get{manager_name}CreateField(fieldName){{const fields={fields_js};return fields[fieldName]||null;}}",
            f"function get{manager_name}CreateFieldDescriptors(fieldName){{const descriptors={descriptors_js};return descriptors[fieldName]||[];}}",
            f"function set{manager_name}CreateFieldError(fieldName,message){{const field=get{manager_name}CreateField(fieldName);const descriptors=get{manager_name}CreateFieldDescriptors(fieldName);const errorId=descriptors.find((id)=>id.endsWith('-error'));const errorNode=errorId?document.getElementById(errorId):null;if(errorNode){{errorNode.textContent=message||'';errorNode.hidden=!message;}}if(field)field.setAttribute('aria-describedby',descriptors.join(' '));}}",
            f"function set{manager_name}CreateFieldState(fieldName,isInvalid,message=''){{const field=get{manager_name}CreateField(fieldName);if(!field)return;field.classList.toggle('field-invalid',!!isInvalid);field.setAttribute('aria-invalid',isInvalid?'true':'false');set{manager_name}CreateFieldError(fieldName,isInvalid?message:'');}}",
            f"function clear{manager_name}CreateFieldState(){{for(const name of Object.keys({fields_js}))set{manager_name}CreateFieldState(name,false,'');}}",
            f"function focus{manager_name}CreateField(fieldName){{const field=get{manager_name}CreateField(fieldName);if(!field)return;field.focus();if(typeof field.select==='function'&&(field.tagName==='INPUT'||field.tagName==='TEXTAREA'))field.select();}}",
        ]
    )


def _runtime_reports_index_html(
    reports: list[dict[str, Any]],
    *,
    auth_session: FrontendAuthSession,
    base_url_choices: list[dict[str, str]] | None = None,
) -> str:
    report_create_field_helper_js = _render_create_field_helper_js(
        manager_name="Report",
        fields_js="{name:reportNameInput,base_url:baseUrlSelect,timeout:document.getElementById('report-timeout')}",
        descriptors_js="{name:['report-name-help','report-name-error'],base_url:['report-base-url-help','report-base-url-error'],timeout:['report-timeout-help','report-timeout-error']}",
    )

    def _report_row(report: dict[str, Any], *, is_latest: bool) -> str:
        row_class = " class='latest-row'" if is_latest else ""
        latest_badge = " <span class='badge'>latest</span>" if is_latest else ""
        name = str(report.get("name") or "unknown")
        html_href = "/runtime/reports/latest" if is_latest else str(report["html_url"])
        safe_name = escape(name, quote=True)
        return (
            f"<tr{row_class} id='report-row-{safe_name}' data-report-name='{safe_name}'>"
            f"<td data-report-col='name'><a href=\"{escape(html_href, quote=True)}\">{escape(name)}</a>{latest_badge}</td>"
            f"<td data-report-col='status'>{escape(str(report.get('status') or 'unknown'))}</td>"
            f"<td data-report-col='summary'>{escape(str(report.get('summary') or ''))}</td>"
            f"<td data-report-col='fetched'><code>{escape(str(report.get('fetched_at') or ''))}</code></td>"
            f"<td data-report-col='links'><a href=\"{escape(str(report['markdown_url']), quote=True)}\">md</a> "
            f"<a href=\"{escape(str(report['json_url']), quote=True)}\">json</a></td>"
            "<td>"
            f"<button class='action-button' data-report-rename-toggle='{safe_name}'>rename</button> "
            f"<button class='action-button danger' data-report-delete='{safe_name}'>delete</button>"
            f"<div class='rename-row' id='rename-row-{safe_name}' hidden>"
            f"<input class='inline-input' id='rename-input-{safe_name}' value=\"{escape(name, quote=True)}\" aria-label='Rename {escape(name, quote=True)}' />"
            f"<button class='action-button' data-report-rename-save='{safe_name}'>save</button> "
            f"<button class='action-button secondary' data-report-rename-cancel='{safe_name}'>cancel</button>"
            "</div>"
            f"<div class='inline-state' id='report-row-state-{safe_name}' aria-live='polite'></div>"
            f"<div class='hint bad' id='report-row-error-{safe_name}' hidden></div>"
            "</td>"
            "</tr>"
        )

    header_links = ""
    options_parts: list[str] = []
    for choice in base_url_choices or []:
        audience = str(choice.get("audience") or "configured")
        base_url = str(choice.get("base_url") or "").strip()
        if not base_url:
            continue
        options_parts.append(
            f"<option value=\"{escape(base_url, quote=True)}\">{escape(audience)} · {escape(base_url)}</option>"
        )
    if not options_parts:
        options_parts.append("<option value=''>Current browser origin</option>")
    if reports:
        header_links = (
            "<div class='latest-links'>"
            "<a href=\"/runtime/reports/latest\">open latest</a> "
            "<a href=\"/v1/runtime/reports/latest\">latest manifest</a>"
            "</div>"
        )
        rows = "".join(_report_row(report, is_latest=index == 0) for index, report in enumerate(reports))
    else:
        rows = '<tr id="report-empty-row"><td colspan="6">No managed runtime reports are available yet.</td></tr>'
    table = (
        "<table><thead><tr><th>Name</th><th>Status</th><th>Summary</th><th>Fetched</th><th>Links</th><th>Actions</th></tr></thead>"
        f"<tbody id='report-table-body'>{rows}</tbody></table>"
    )

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Slack Mirror Runtime Reports</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<style>"
        ":root{--bg:#f4efe7;--panel:#fffdf9;--ink:#122033;--muted:#5f6c7b;--line:#d9d0c3;--accent:#0b57d0;--bad:#a12828;--bad-soft:#fde5e5;--ok:#1f7a44;--ok-soft:#ddefe3;--warn:#a05a00;--warn-soft:#fff0db;--shadow:0 14px 30px rgba(18,32,51,.08);}"
        "*{box-sizing:border-box}body{margin:0;font-family:\"Aptos\",\"Segoe UI\",Arial,sans-serif;background:linear-gradient(180deg,#f6f1e9 0,#efe7dc 100%);color:var(--ink)}"
        f"{_authenticated_topbar_css()}"
        ".shell{max-width:1180px;margin:0 auto;padding:28px 18px 40px}"
        "h1{margin:0 0 12px}"
        "p{line-height:1.5}"
        ".layout{display:grid;grid-template-columns:minmax(320px,420px) 1fr;gap:18px;align-items:start}"
        ".panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:var(--shadow)}"
        ".panel h2{margin:0 0 12px;font-size:18px}"
        ".feedback{display:none;margin:0 0 16px;padding:10px 12px;border-radius:10px;font-size:14px}"
        ".feedback.show{display:block}.feedback.ok{background:#ecfdf3;border:1px solid #b7ebc6;color:#166534}.feedback.bad{background:#fef2f2;border:1px solid #fecaca;color:#b91c1c}"
        "label{display:block;margin:12px 0 6px;font-weight:600}"
        "input,select{width:100%;padding:10px 12px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px;background:#fff}"
        ".submit-button,.action-button{padding:9px 12px;border-radius:10px;border:1px solid #b7c9ee;background:#edf4ff;color:#0b57d0;font-weight:700;cursor:pointer}"
        ".action-button{padding:7px 10px;font-size:12px}.action-button.secondary{background:#fff;border-color:#cbd5e1;color:#334155}.action-button.danger{background:#fff1f2;border-color:#fecdd3;color:#be123c}"
        ".preset-row,.rename-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center}"
        ".preset-chip{padding:7px 10px;border-radius:999px;border:1px solid #cbd5e1;background:#fff;color:#334155;font-weight:600;cursor:pointer}"
        ".inline-input{min-width:220px;flex:1}"
        ".hint{margin:8px 0 0;color:#475569;font-size:13px}"
        ".field-invalid{border-color:#dc2626 !important;box-shadow:0 0 0 3px rgba(220,38,38,.12)}"
        ".inline-state{display:none;margin-top:8px;font-size:12px;font-weight:700}"
        ".inline-state.show{display:inline-flex;align-items:center;gap:6px}"
        ".inline-state.ok{color:#166534}.inline-state.bad{color:#b91c1c}"
        f"{_BROWSER_DIALOG_CSS}"
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
        "@media (max-width:900px){.layout{grid-template-columns:1fr}}"
        "</style></head><body><div class='shell'>"
        f"{_authenticated_topbar_html(auth_session=auth_session, current_path='/runtime/reports')}"
        "<h1>Slack Mirror Runtime Reports</h1>"
        "<p>Latest managed runtime snapshots published by <code>user-env snapshot-report</code>. The newest report is highlighted and linked through the stable <code>/runtime/reports/latest</code> alias.</p>"
        "<div id='report-feedback' class='feedback' role='status' aria-live='polite'></div>"
        "<div class='layout'>"
        "<section class='panel'>"
        "<h2>Create runtime report</h2>"
        "<label for='report-name'>Report name</label>"
        "<input id='report-name' placeholder='ops-snapshot' aria-describedby='report-name-help report-name-error' />"
        "<div class='hint' id='report-name-help'>Pick a stable snapshot name such as <code>morning-ops</code>.</div>"
        "<div class='hint bad' id='report-name-error' hidden></div>"
        "<div class='preset-row'>"
        "<button type='button' class='preset-chip' data-report-name-preset='morning-ops'>morning-ops</button>"
        "<button type='button' class='preset-chip' data-report-name-preset='daily-ops'>daily-ops</button>"
        "<button type='button' class='preset-chip' data-report-name-preset='scheduled-runtime-report'>scheduled-runtime-report</button>"
        "<button type='button' class='preset-chip' id='timestamped-report-name'>timestamped</button>"
        "</div>"
        "<label for='report-base-url-select'>Base URL</label>"
        f"<select id='report-base-url-select'>{''.join(options_parts)}</select>"
        "<p class='hint' id='report-base-url-help'>Choose one of the configured publish origins for this snapshot.</p>"
        "<div class='hint bad' id='report-base-url-error' hidden></div>"
        "<label for='report-timeout'>Timeout seconds</label>"
        "<input id='report-timeout' type='number' step='0.1' value='5' aria-describedby='report-timeout-help report-timeout-error' />"
        "<div class='hint' id='report-timeout-help'>Use a short timeout for bounded snapshot generation.</div>"
        "<div class='hint bad' id='report-timeout-error' hidden></div>"
        "<button id='create-report-button' class='submit-button'>Create runtime report</button>"
        "<div class='hint bad' id='report-create-error' hidden aria-live='polite'></div>"
        "</section>"
        "<section>"
        f"{header_links}"
        f"{table}"
        "</section>"
        "</div>"
        "<script>"
        "const reportFeedback=document.getElementById('report-feedback');"
        "const reportCreateError=document.getElementById('report-create-error');"
        "function setReportFeedback(message,isError){reportFeedback.textContent=message;reportFeedback.className=`feedback show ${isError?'bad':'ok'}`;}"
        "function setReportCreateError(message){if(!reportCreateError)return;if(message){reportCreateError.textContent=message;reportCreateError.hidden=false;return;}reportCreateError.textContent='';reportCreateError.hidden=true;}"
        f"{report_create_field_helper_js}"
        f"{_BROWSER_ESCAPE_HTML_JS}"
        f"{_BROWSER_BUSY_LABEL_JS}"
        f"{_BROWSER_FETCH_JSON_HELPERS_JS}"
        f"{_BROWSER_DIALOG_JS}"
        f"{_INLINE_MANAGER_JS}"
        "function reportRowHtml(report,isLatest){const safeName=escapeHtml(report.name||'unknown');const htmlHref=isLatest?'/runtime/reports/latest':String(report.html_url||`/runtime/reports/${encodeURIComponent(report.name||'unknown')}`);const latestBadge=isLatest?\" <span class='badge'>latest</span>\":'';const rowClass=isLatest?\" class='latest-row'\":'';return `<tr${rowClass} id=\"report-row-${safeName}\" data-report-name=\"${safeName}\"><td data-report-col=\"name\"><a href=\"${escapeHtml(htmlHref)}\">${safeName}</a>${latestBadge}</td><td data-report-col=\"status\">${escapeHtml(report.status||'unknown')}</td><td data-report-col=\"summary\">${escapeHtml(report.summary||'')}</td><td data-report-col=\"fetched\"><code>${escapeHtml(report.fetched_at||'')}</code></td><td data-report-col=\"links\"><a href=\"${escapeHtml(report.markdown_url||'')}\">md</a> <a href=\"${escapeHtml(report.json_url||'')}\">json</a></td><td><button class=\"action-button\" data-report-rename-toggle=\"${safeName}\">rename</button> <button class=\"action-button danger\" data-report-delete=\"${safeName}\">delete</button><div class=\"rename-row\" id=\"rename-row-${safeName}\" hidden><input class=\"inline-input\" id=\"rename-input-${safeName}\" value=\"${safeName}\" aria-label=\"Rename ${safeName}\" /><button class=\"action-button\" data-report-rename-save=\"${safeName}\">save</button> <button class=\"action-button secondary\" data-report-rename-cancel=\"${safeName}\">cancel</button></div><div class=\"inline-state\" id=\"report-row-state-${safeName}\" aria-live=\"polite\"></div><div class=\"hint bad\" id=\"report-row-error-${safeName}\" hidden></div></td></tr>`;}"
        "function clearLatestReportRow(){const row=document.querySelector('#report-table-body .latest-row');if(!row)return;row.classList.remove('latest-row');const nameCell=row.querySelector('[data-report-col=\"name\"]');if(nameCell){const badge=nameCell.querySelector('.badge');if(badge)badge.remove();const link=nameCell.querySelector('a');const name=row.dataset.reportName||'';if(link&&name){link.setAttribute('href',`/runtime/reports/${encodeURIComponent(name)}`);}}}"
        "function ensureReportEmptyStateRow(){const tbody=document.getElementById('report-table-body');if(!tbody)return;const empty=document.getElementById('report-empty-row');if(empty)return;const row=document.createElement('tr');row.id='report-empty-row';row.innerHTML='<td colspan=\"6\">No managed runtime reports are available yet.</td>';tbody.append(row);}"
        "function ensureReportTableBody(){return document.getElementById('report-table-body');}"
        "function insertCreatedReport(report){const tbody=ensureReportTableBody();if(!tbody)return;const empty=document.getElementById('report-empty-row');if(empty)empty.remove();clearLatestReportRow();const wrapper=document.createElement('tbody');wrapper.innerHTML=reportRowHtml(report,true);const row=wrapper.firstElementChild;if(!row)return;tbody.prepend(row);bindReportRowActions(row);}"
        "function timestampedReportName(){const now=new Date();const pad=(v)=>String(v).padStart(2,'0');return `ops-${now.getUTCFullYear()}${pad(now.getUTCMonth()+1)}${pad(now.getUTCDate())}-${pad(now.getUTCHours())}${pad(now.getUTCMinutes())}${pad(now.getUTCSeconds())}`;}"
        "const reportNameInput=document.getElementById('report-name');"
        "const createReportButton=document.getElementById('create-report-button');"
        "if(!reportNameInput.value.trim())reportNameInput.value=timestampedReportName();"
        "for(const button of document.querySelectorAll('[data-report-name-preset]')){button.addEventListener('click',()=>{reportNameInput.value=button.getAttribute('data-report-name-preset')||'';reportNameInput.focus();});}"
        "document.getElementById('timestamped-report-name').addEventListener('click',()=>{reportNameInput.value=timestampedReportName();reportNameInput.focus();});"
        "const baseUrlSelect=document.getElementById('report-base-url-select');"
        "if(baseUrlSelect && !baseUrlSelect.value){baseUrlSelect.value=window.location.origin;}"
        "function validateReportCreateForm(name,baseUrl,timeout){if(!name)return {field:'name',message:'Report name is required'};if(!baseUrl)return {field:'base_url',message:'Base URL is required'};if(!Number.isFinite(timeout)||timeout<=0)return {field:'timeout',message:'Timeout seconds must be greater than zero'};return null;}"
        "function setCreateReportBusyState(isBusy){if(createReportButton){createReportButton.disabled=isBusy;setButtonBusyLabel(createReportButton,isBusy,'creating…');}reportNameInput.disabled=isBusy;if(baseUrlSelect)baseUrlSelect.disabled=isBusy;const timeoutInput=document.getElementById('report-timeout');if(timeoutInput)timeoutInput.disabled=isBusy;for(const button of document.querySelectorAll('[data-report-name-preset]'))button.disabled=isBusy;const stampButton=document.getElementById('timestamped-report-name');if(stampButton)stampButton.disabled=isBusy;}"
        "reportNameInput.addEventListener('input',()=>{setReportCreateError('');setReportCreateFieldState('name',false,'');});"
        "if(baseUrlSelect)baseUrlSelect.addEventListener('change',()=>{setReportCreateError('');setReportCreateFieldState('base_url',false,'');});"
        "const reportTimeoutInput=document.getElementById('report-timeout');"
        "if(reportTimeoutInput)reportTimeoutInput.addEventListener('input',()=>{setReportCreateError('');setReportCreateFieldState('timeout',false,'');});"
        "document.getElementById('create-report-button').addEventListener('click',async()=>{"
        "if(createReportButton?.disabled)return;"
        "const name=reportNameInput.value.trim();"
        "const baseUrl=(baseUrlSelect?.value||'').trim()||window.location.origin;"
        "const timeout=Number(document.getElementById('report-timeout').value||'5');"
        "const validationError=validateReportCreateForm(name,baseUrl,timeout);"
        "clearReportCreateFieldState();"
        "if(validationError){setReportCreateFieldState(validationError.field,true,validationError.message);setReportCreateError(validationError.message);setReportFeedback(validationError.message,true);focusReportCreateField(validationError.field);return;}"
        "setCreateReportBusyState(true);"
        "try{const {resp,data}=await fetchJsonResponse('/v1/runtime/reports',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({name,base_url:baseUrl,timeout})});if(resp.ok){clearReportCreateFieldState();setReportCreateError('');if(data?.report){insertCreatedReport(data.report);reportNameInput.value=timestampedReportName();setReportFeedback(`Created runtime report ${data.report.name}.`,false);return;}setReportFeedback('Created runtime report.',false);return;}const message=responseErrorMessage(data,'Create failed');setReportCreateError(message);setReportFeedback(message,true);}finally{setCreateReportBusyState(false);}"
        "});"
        "function bindReportRowActions(scope){bindInlineManagerActions(scope,{renameToggleAttr:'data-report-rename-toggle',renameCancelAttr:'data-report-rename-cancel',renameSaveAttr:'data-report-rename-save',deleteAttr:'data-report-delete',renameInputPrefix:'rename-input-',renameRowPrefix:'rename-row-',rowStatePrefix:'report-row-state-',rowErrorPrefix:'report-row-error-',renamePath:(current)=>`/v1/runtime/reports/${encodeURIComponent(current)}/rename`,renameBody:(next)=>({name:next}),deletePath:(current)=>`/v1/runtime/reports/${encodeURIComponent(current)}`,deleteConfirm:(current)=>`Delete runtime report ${current}?`,applyRename:applyReportRename,removeRow:removeReportRow,setFeedback:setReportFeedback,itemLabel:'runtime report'});}"
        "function applyReportRename(current,next){const row=document.getElementById(`report-row-${current}`);if(!row)return;row.id=`report-row-${next}`;row.dataset.reportName=next;const nameCell=row.querySelector('[data-report-col=\"name\"]');if(nameCell){nameCell.innerHTML=`<a href=\"/runtime/reports/${encodeURIComponent(next)}\">${escapeHtml(next)}</a>`;}const linksCell=row.querySelector('[data-report-col=\"links\"]');if(linksCell){linksCell.innerHTML=`<a href=\"/runtime/reports/${encodeURIComponent(next)}.latest.md\">md</a> <a href=\"/runtime/reports/${encodeURIComponent(next)}.latest.json\">json</a>`;}for(const el of row.querySelectorAll('[data-report-rename-toggle]'))el.setAttribute('data-report-rename-toggle',next);for(const el of row.querySelectorAll('[data-report-rename-save]'))el.setAttribute('data-report-rename-save',next);for(const el of row.querySelectorAll('[data-report-rename-cancel]'))el.setAttribute('data-report-rename-cancel',next);for(const el of row.querySelectorAll('[data-report-delete]'))el.setAttribute('data-report-delete',next);const renameRow=document.getElementById(`rename-row-${current}`);if(renameRow){renameRow.id=`rename-row-${next}`;renameRow.hidden=true;}const renameInput=document.getElementById(`rename-input-${current}`);if(renameInput){renameInput.id=`rename-input-${next}`;renameInput.value=next;renameInput.setAttribute('aria-label',`Rename ${next}`);}const rowState=document.getElementById(`report-row-state-${current}`);if(rowState){rowState.id=`report-row-state-${next}`;rowState.className='inline-state';rowState.textContent='';}const rowError=document.getElementById(`report-row-error-${current}`);if(rowError){rowError.id=`report-row-error-${next}`;rowError.hidden=true;rowError.textContent='';}}"
        "function removeReportRow(name){const row=document.getElementById(`report-row-${name}`);if(row)row.remove();const tbody=document.getElementById('report-table-body');if(tbody&&!tbody.querySelector('tr'))ensureReportEmptyStateRow();}"
        "bindReportRowActions(document);"
        "</script>"
        "</div></body></html>"
    )


def _exports_index_html(exports: list[dict[str, Any]]) -> str:
    export_create_field_helper_js = _render_create_field_helper_js(
        manager_name="Export",
        fields_js="{workspace:workspaceSelect,channel:channelSelect,day:dayInput,tz:document.getElementById('export-tz'),audience:document.getElementById('export-audience')}",
        descriptors_js="{workspace:['export-workspace-help','export-workspace-error'],channel:['export-channel-meta','export-channel-error'],day:['export-day-help','export-day-error'],tz:['export-tz-help','export-tz-error'],audience:['export-audience-help','export-audience-error']}",
    )

    def _export_row(item: dict[str, Any]) -> str:
        export_id = str(item.get("export_id") or "unknown")
        safe_export_id = escape(export_id, quote=True)
        workspace = escape(str(item.get("workspace") or "unknown"))
        channel = escape(str(item.get("channel") or item.get("channel_id") or "unknown"))
        return (
            f"<tr id='export-row-{safe_export_id}' data-export-id='{safe_export_id}'>"
            f"<td data-export-col='name'><a href=\"/exports/{safe_export_id}\">{escape(export_id)}</a></td>"
            f"<td data-export-col='scope'><code>{workspace}</code> <code>{channel}</code></td>"
            f"<td data-export-col='day'>{escape(str(item.get('day') or ''))}</td>"
            f"<td data-export-col='files'>{int(item.get('attachment_count', 0) or 0)} attachments · {int(item.get('file_count', 0) or 0)} files</td>"
            f"<td data-export-col='manifest'><a href=\"/v1/exports/{safe_export_id}\">manifest</a></td>"
            "<td>"
            f"<button class='action-button' data-export-rename-toggle='{safe_export_id}'>rename</button> "
            f"<button class='action-button danger' data-export-delete='{safe_export_id}'>delete</button>"
            f"<div class='rename-row' id='export-rename-row-{safe_export_id}' hidden>"
            f"<input class='inline-input' id='export-rename-input-{safe_export_id}' value=\"{safe_export_id}\" aria-label='Rename {safe_export_id}' />"
            f"<button class='action-button' data-export-rename-save='{safe_export_id}'>save</button> "
            f"<button class='action-button secondary' data-export-rename-cancel='{safe_export_id}'>cancel</button>"
            "</div>"
            f"<div class='inline-state' id='export-row-state-{safe_export_id}' aria-live='polite'></div>"
            f"<div class='hint bad' id='export-row-error-{safe_export_id}' hidden></div>"
            "</td>"
            "</tr>"
        )

    rows_parts: list[str] = []
    for item in exports:
        rows_parts.append(_export_row(item))
    table = (
        "<table><thead><tr><th>Export</th><th>Scope</th><th>Day</th><th>Files</th><th>Links</th><th>Actions</th></tr></thead>"
        f"<tbody id='export-table-body'>{''.join(rows_parts) if rows_parts else '<tr id=\"export-empty-row\"><td colspan=\"6\">No managed exports published yet.</td></tr>'}</tbody></table>"
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Slack Mirror Exports</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<style>"
        "body{font-family:Arial,sans-serif;margin:24px;background:#f8fafc;color:#0f172a}"
        "h1{margin:0 0 12px}"
        "p{line-height:1.5}"
        ".layout{display:grid;grid-template-columns:minmax(320px,430px) 1fr;gap:18px;align-items:start}"
        ".panel{background:#fff;border:1px solid #dbe2ea;border-radius:16px;padding:18px;box-shadow:0 10px 24px rgba(15,23,42,.06)}"
        ".panel h2{margin:0 0 12px;font-size:18px}"
        ".feedback{display:none;margin:0 0 16px;padding:10px 12px;border-radius:10px;font-size:14px}"
        ".feedback.show{display:block}.feedback.ok{background:#ecfdf3;border:1px solid #b7ebc6;color:#166534}.feedback.bad{background:#fef2f2;border:1px solid #fecaca;color:#b91c1c}"
        "label{display:block;margin:12px 0 6px;font-weight:600}"
        "input,select{width:100%;padding:10px 12px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px}"
        ".submit-button,.action-button{padding:9px 12px;border-radius:10px;border:1px solid #b7c9ee;background:#edf4ff;color:#0b57d0;font-weight:700;cursor:pointer}"
        ".action-button{padding:7px 10px;font-size:12px}.action-button.secondary{background:#fff;border-color:#cbd5e1;color:#334155}.action-button.danger{background:#fff1f2;border-color:#fecdd3;color:#be123c}"
        ".rename-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center}"
        ".inline-input{min-width:220px;flex:1}"
        ".meta{color:#475569;font-size:13px;line-height:1.45}"
        ".field-invalid{border-color:#dc2626 !important;box-shadow:0 0 0 3px rgba(220,38,38,.12)}"
        ".inline-state{display:none;margin-top:8px;font-size:12px;font-weight:700}"
        ".inline-state.show{display:inline-flex;align-items:center;gap:6px}"
        ".inline-state.ok{color:#166534}.inline-state.bad{color:#b91c1c}"
        f"{_BROWSER_DIALOG_CSS}"
        "table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #dbe2ea;border-radius:12px;overflow:hidden}"
        "th,td{padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:left;vertical-align:top}"
        "th{background:#e2e8f0}"
        "tr:last-child td{border-bottom:none}"
        "a{color:#0b57d0;text-decoration:none}"
        "a:hover{text-decoration:underline}"
        "code{background:#e2e8f0;padding:1px 5px;border-radius:6px}"
        "@media (max-width:900px){.layout{grid-template-columns:1fr}}"
        "</style></head><body>"
        "<h1>Slack Mirror Exports</h1>"
        "<p>Create and manage published channel-day export bundles from the browser. This page is intentionally bounded to the existing managed export contract.</p>"
        "<div id='export-feedback' class='feedback' role='status' aria-live='polite'></div>"
        "<div class='layout'>"
        "<section class='panel'>"
        "<h2>Create channel-day export</h2>"
        "<label for='export-workspace'>Workspace</label>"
        "<select id='export-workspace'><option value=''>Loading workspaces…</option></select>"
        "<div class='hint' id='export-workspace-help'>Choose one of the mirrored workspaces available in this install.</div>"
        "<div class='hint bad' id='export-workspace-error' hidden></div>"
        "<label for='export-channel-filter'>Filter channels</label>"
        "<input id='export-channel-filter' placeholder='Search by name, id, or class' disabled aria-describedby='export-channel-filter-help' />"
        "<div class='hint' id='export-channel-filter-help'>Filter the valid mirrored channel list before selecting a channel.</div>"
        "<div id='export-channel-filter-meta' class='meta' style='margin-top:8px'>Load a workspace to filter valid channel choices.</div>"
        "<label for='export-channel'>Channel</label>"
        "<select id='export-channel' disabled><option value=''>Choose a workspace first</option></select>"
        "<div class='hint bad' id='export-channel-error' hidden></div>"
        "<div id='export-channel-meta' class='meta' style='margin-top:8px'>Select a workspace to load valid channel choices.</div>"
        "<label for='export-day'>Day</label>"
        "<input id='export-day' type='date' aria-describedby='export-day-help export-day-error' />"
        "<div class='hint' id='export-day-help'>Use a mirrored day for the selected channel in <code>YYYY-MM-DD</code> form.</div>"
        "<div class='hint bad' id='export-day-error' hidden></div>"
        "<label for='export-tz'>Timezone</label>"
        "<input id='export-tz' value='America/Chicago' aria-describedby='export-tz-help export-tz-error' />"
        "<div class='hint' id='export-tz-help'>Timezone controls report-local rendering for the exported day.</div>"
        "<div class='hint bad' id='export-tz-error' hidden></div>"
        "<label for='export-audience'>Audience</label>"
        "<select id='export-audience'><option value='local'>local</option><option value='external'>external</option></select>"
        "<div class='hint' id='export-audience-help'>Choose which configured URL audience the browser will prefer after create.</div>"
        "<div class='hint bad' id='export-audience-error' hidden></div>"
        "<label for='export-id'>Optional export id</label>"
        "<input id='export-id' placeholder='channel-day-default-general-2026-04-13-abc123' />"
        "<button id='create-export-button' class='submit-button'>Create channel-day export</button>"
        "<div class='hint bad' id='export-create-error' hidden aria-live='polite'></div>"
        "</section>"
        f"<section>{table}</section>"
        "</div>"
        "<script>"
        "const exportFeedback=document.getElementById('export-feedback');"
        "const exportCreateError=document.getElementById('export-create-error');"
        "const workspaceSelect=document.getElementById('export-workspace');"
        "const channelFilterInput=document.getElementById('export-channel-filter');"
        "const channelFilterMeta=document.getElementById('export-channel-filter-meta');"
        "const channelSelect=document.getElementById('export-channel');"
        "const channelMeta=document.getElementById('export-channel-meta');"
        "const dayInput=document.getElementById('export-day');"
        "const createExportButton=document.getElementById('create-export-button');"
        "let workspaceChannels=[];"
        "function setExportFeedback(message,isError){exportFeedback.textContent=message;exportFeedback.className=`feedback show ${isError?'bad':'ok'}`;}"
        "function setExportCreateError(message){if(!exportCreateError)return;if(message){exportCreateError.textContent=message;exportCreateError.hidden=false;return;}exportCreateError.textContent='';exportCreateError.hidden=true;}"
        f"{export_create_field_helper_js}"
        f"{_BROWSER_BUSY_LABEL_JS}"
        f"{_BROWSER_FETCH_JSON_HELPERS_JS}"
        f"{_BROWSER_DIALOG_JS}"
        f"{_INLINE_MANAGER_JS}"
        "function channelSearchText(item){return [item.name,item.channel_id,item.channel_class,item.latest_message_day].filter(Boolean).join(' ').toLowerCase();}"
        "function updateChannelSelectionMeta(){const selected=workspaceChannels.find((item)=>item.name===channelSelect.value);if(!selected){channelMeta.textContent='Choose a valid mirrored channel for export creation.';return;}channelMeta.textContent=`${selected.channel_class} · ${selected.message_count} messages mirrored${selected.latest_message_day?` · latest day ${selected.latest_message_day}`:''}`;if(selected.latest_message_day){dayInput.value=selected.latest_message_day;}}"
        f"{_BROWSER_ESCAPE_HTML_JS}"
        "function renderChannelOptions(){const filter=(channelFilterInput.value||'').trim().toLowerCase();const filtered=workspaceChannels.filter((item)=>!filter||channelSearchText(item).includes(filter));const previous=channelSelect.value;channelSelect.innerHTML='';if(!workspaceChannels.length){channelSelect.disabled=true;channelFilterInput.disabled=true;channelSelect.innerHTML='<option value=\"\">No mirrored channels available</option>';channelMeta.textContent='No mirrored channels were found for this workspace.';channelFilterMeta.textContent='No channel choices are available for filtering.';return;}channelFilterInput.disabled=false;if(!filtered.length){channelSelect.disabled=true;channelSelect.innerHTML='<option value=\"\">No channels match this filter</option>';channelMeta.textContent='Adjust the channel filter to see valid choices.';channelFilterMeta.textContent=`0 of ${workspaceChannels.length} mirrored channels match.`;return;}channelSelect.disabled=false;channelSelect.innerHTML='<option value=\"\">Choose a channel…</option>'+filtered.map((item)=>`<option value=\"${item.name}\">${item.name} · ${item.channel_class} · ${item.message_count} msgs</option>`).join('');channelFilterMeta.textContent=`${filtered.length} of ${workspaceChannels.length} mirrored channels match.`;if(filtered.some((item)=>item.name===previous)){channelSelect.value=previous;}channelMeta.textContent='Choose a valid mirrored channel for export creation.';if(channelSelect.value){updateChannelSelectionMeta();}}"
        "async function loadChannels(workspace){channelSelect.disabled=true;channelFilterInput.disabled=true;channelFilterInput.value='';channelSelect.innerHTML='<option value=\"\">Loading channels…</option>';channelMeta.textContent='Loading mirrored channels…';channelFilterMeta.textContent='Loading valid channel choices…';const {resp,data}=await fetchJsonResponse(`/v1/workspaces/${encodeURIComponent(workspace)}/channels`);if(!resp.ok){setExportFeedback(responseErrorMessage(data,'Failed to load channels'),true);workspaceChannels=[];renderChannelOptions();return;}workspaceChannels=data?.channels||[];renderChannelOptions();}"
        "async function loadWorkspaces(){const {resp,data}=await fetchJsonResponse('/v1/workspaces');if(!resp.ok){setExportFeedback(responseErrorMessage(data,'Failed to load workspaces'),true);workspaceSelect.innerHTML='<option value=\"\">Unable to load workspaces</option>';return;}const workspaces=data?.workspaces||[];workspaceSelect.innerHTML='<option value=\"\">Choose a workspace…</option>'+workspaces.map((item)=>`<option value=\"${item.name}\">${item.name}</option>`).join('');if(workspaces.length){workspaceSelect.value=workspaces[0].name;await loadChannels(workspaces[0].name);}}"
        "workspaceSelect.addEventListener('change',async()=>{const workspace=workspaceSelect.value.trim();dayInput.value='';if(!workspace){workspaceChannels=[];channelFilterInput.value='';renderChannelOptions();return;}await loadChannels(workspace);});"
        "channelFilterInput.addEventListener('input',()=>{renderChannelOptions();});"
        "channelSelect.addEventListener('change',()=>{updateChannelSelectionMeta();});"
        "function exportRowHtml(item){const exportId=escapeHtml(item.export_id||'unknown');const workspace=escapeHtml(item.workspace||'unknown');const channel=escapeHtml(item.channel||item.channel_id||'unknown');const day=escapeHtml(item.day||'');const attachmentCount=Number(item.attachment_count||0);const fileCount=Number(item.file_count||0);return `<tr id=\"export-row-${exportId}\" data-export-id=\"${exportId}\"><td data-export-col=\"name\"><a href=\"/exports/${encodeURIComponent(item.export_id||'unknown')}\">${exportId}</a></td><td data-export-col=\"scope\"><code>${workspace}</code> <code>${channel}</code></td><td data-export-col=\"day\">${day}</td><td data-export-col=\"files\">${attachmentCount} attachments · ${fileCount} files</td><td data-export-col=\"manifest\"><a href=\"/v1/exports/${encodeURIComponent(item.export_id||'unknown')}\">manifest</a></td><td><button class=\"action-button\" data-export-rename-toggle=\"${exportId}\">rename</button> <button class=\"action-button danger\" data-export-delete=\"${exportId}\">delete</button><div class=\"rename-row\" id=\"export-rename-row-${exportId}\" hidden><input class=\"inline-input\" id=\"export-rename-input-${exportId}\" value=\"${exportId}\" aria-label=\"Rename ${exportId}\" /><button class=\"action-button\" data-export-rename-save=\"${exportId}\">save</button> <button class=\"action-button secondary\" data-export-rename-cancel=\"${exportId}\">cancel</button></div><div class=\"inline-state\" id=\"export-row-state-${exportId}\" aria-live=\"polite\"></div><div class=\"hint bad\" id=\"export-row-error-${exportId}\" hidden></div></td></tr>`;}"
        "function ensureExportEmptyStateRow(){const tbody=document.getElementById('export-table-body');if(!tbody)return;const empty=document.getElementById('export-empty-row');if(empty)return;const row=document.createElement('tr');row.id='export-empty-row';row.innerHTML='<td colspan=\"6\">No managed exports published yet.</td>';tbody.append(row);}"
        "function insertCreatedExport(item){const tbody=document.getElementById('export-table-body');if(!tbody||!item)return;const empty=document.getElementById('export-empty-row');if(empty)empty.remove();const wrapper=document.createElement('tbody');wrapper.innerHTML=exportRowHtml(item);const row=wrapper.firstElementChild;if(!row)return;tbody.prepend(row);bindExportRowActions(row);}"
        "function validateExportCreatePayload(payload){if(!payload.workspace)return {field:'workspace',message:'Workspace is required'};if(!payload.channel)return {field:'channel',message:'Channel is required'};if(!payload.day)return {field:'day',message:'Day is required'};if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(payload.day))return {field:'day',message:'Day must use YYYY-MM-DD'};if(!payload.tz)return {field:'tz',message:'Timezone is required'};if(!payload.audience)return {field:'audience',message:'Audience is required'};return null;}"
        "function setCreateExportBusyState(isBusy){if(createExportButton){createExportButton.disabled=isBusy;setButtonBusyLabel(createExportButton,isBusy,'creating…');}workspaceSelect.disabled=isBusy;channelFilterInput.disabled=isBusy||!workspaceChannels.length;channelSelect.disabled=isBusy||channelSelect.options.length<=1;dayInput.disabled=isBusy;const tzInput=document.getElementById('export-tz');if(tzInput)tzInput.disabled=isBusy;const audienceSelect=document.getElementById('export-audience');if(audienceSelect)audienceSelect.disabled=isBusy;const exportIdInput=document.getElementById('export-id');if(exportIdInput)exportIdInput.disabled=isBusy;}"
        "workspaceSelect.addEventListener('change',()=>{setExportCreateError('');setExportCreateFieldState('workspace',false,'');});"
        "channelFilterInput.addEventListener('input',()=>setExportCreateError(''));"
        "channelSelect.addEventListener('change',()=>{setExportCreateError('');setExportCreateFieldState('channel',false,'');});"
        "dayInput.addEventListener('input',()=>{setExportCreateError('');setExportCreateFieldState('day',false,'');});"
        "const exportTzInput=document.getElementById('export-tz');"
        "if(exportTzInput)exportTzInput.addEventListener('input',()=>{setExportCreateError('');setExportCreateFieldState('tz',false,'');});"
        "const exportAudienceSelect=document.getElementById('export-audience');"
        "if(exportAudienceSelect)exportAudienceSelect.addEventListener('change',()=>{setExportCreateError('');setExportCreateFieldState('audience',false,'');});"
        "const exportIdField=document.getElementById('export-id');"
        "if(exportIdField)exportIdField.addEventListener('input',()=>setExportCreateError(''));"
        "document.getElementById('create-export-button').addEventListener('click',async()=>{"
        "if(createExportButton?.disabled)return;"
        "const payload={kind:'channel-day',workspace:workspaceSelect.value.trim(),channel:channelSelect.value.trim(),day:dayInput.value.trim(),tz:document.getElementById('export-tz').value.trim()||'America/Chicago',audience:document.getElementById('export-audience').value,export_id:document.getElementById('export-id').value.trim()||undefined};"
        "const validationError=validateExportCreatePayload(payload);"
        "clearExportCreateFieldState();"
        "if(validationError){setExportCreateFieldState(validationError.field,true,validationError.message);setExportCreateError(validationError.message);setExportFeedback(validationError.message,true);focusExportCreateField(validationError.field);return;}"
        "setCreateExportBusyState(true);"
        "try{const {resp,data}=await fetchJsonResponse('/v1/exports',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});if(resp.ok){clearExportCreateFieldState();setExportCreateError('');if(data?.export){insertCreatedExport(data.export);document.getElementById('export-id').value='';setExportFeedback(`Created export ${data.export.export_id}.`,false);return;}setExportFeedback('Created export.',false);return;}const message=responseErrorMessage(data,'Create failed');setExportCreateError(message);setExportFeedback(message,true);}finally{setCreateExportBusyState(false);}"
        "});"
        "function bindExportRowActions(scope){bindInlineManagerActions(scope,{renameToggleAttr:'data-export-rename-toggle',renameCancelAttr:'data-export-rename-cancel',renameSaveAttr:'data-export-rename-save',deleteAttr:'data-export-delete',renameInputPrefix:'export-rename-input-',renameRowPrefix:'export-rename-row-',rowStatePrefix:'export-row-state-',rowErrorPrefix:'export-row-error-',renamePath:(current)=>`/v1/exports/${encodeURIComponent(current)}/rename`,renameBody:(next)=>({export_id:next,audience:'local'}),deletePath:(current)=>`/v1/exports/${encodeURIComponent(current)}`,deleteConfirm:(current)=>`Delete export ${current}?`,applyRename:applyExportRename,removeRow:removeExportRow,setFeedback:setExportFeedback,itemLabel:'export'});}"
        "function applyExportRename(current,next){const row=document.getElementById(`export-row-${current}`);if(!row)return;row.id=`export-row-${next}`;row.dataset.exportId=next;const nameCell=row.querySelector('[data-export-col=\"name\"]');if(nameCell){nameCell.innerHTML=`<a href=\"/exports/${encodeURIComponent(next)}\">${escapeHtml(next)}</a>`;}const manifestCell=row.querySelector('[data-export-col=\"manifest\"]');if(manifestCell){manifestCell.innerHTML=`<a href=\"/v1/exports/${encodeURIComponent(next)}\">manifest</a>`;}for(const el of row.querySelectorAll('[data-export-rename-toggle]'))el.setAttribute('data-export-rename-toggle',next);for(const el of row.querySelectorAll('[data-export-rename-save]'))el.setAttribute('data-export-rename-save',next);for(const el of row.querySelectorAll('[data-export-rename-cancel]'))el.setAttribute('data-export-rename-cancel',next);for(const el of row.querySelectorAll('[data-export-delete]'))el.setAttribute('data-export-delete',next);const renameRow=document.getElementById(`export-rename-row-${current}`);if(renameRow){renameRow.id=`export-rename-row-${next}`;renameRow.hidden=true;}const renameInput=document.getElementById(`export-rename-input-${current}`);if(renameInput){renameInput.id=`export-rename-input-${next}`;renameInput.value=next;renameInput.setAttribute('aria-label',`Rename ${next}`);}const rowState=document.getElementById(`export-row-state-${current}`);if(rowState){rowState.id=`export-row-state-${next}`;rowState.className='inline-state';rowState.textContent='';}const rowError=document.getElementById(`export-row-error-${current}`);if(rowError){rowError.id=`export-row-error-${next}`;rowError.hidden=true;rowError.textContent='';}}"
        "function removeExportRow(name){const row=document.getElementById(`export-row-${name}`);if(row)row.remove();const tbody=document.getElementById('export-table-body');if(tbody&&!tbody.querySelector('tr'))ensureExportEmptyStateRow();}"
        "bindExportRowActions(document);"
        "loadWorkspaces();"
        "</script>"
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
            f"<li class='list-row compact'><a href=\"/search\">{code('/search')}</a></li>",
            f"<li class='list-row compact'><a href=\"/v1/search/corpus\">{code('/v1/search/corpus')}</a></li>",
            f"<li class='list-row compact'><a href=\"/exports\">{code('/exports')}</a></li>",
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
        f"{_authenticated_topbar_css()}"
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
        f"{_authenticated_topbar_html(auth_session=auth_session, current_path='/')}"
        "<div class='hero'>"
        "<section class='card hero-card'>"
        "<span class='eyebrow'>Slack Mirror</span>"
        "<h1>Authenticated workspace home</h1>"
        "<p class='lede'>Use this page as the browser entrypoint for runtime health, the freshest ops snapshot, and recent managed exports.</p>"
        f"<div class='status-line'>{''.join(health_badges)}</div>"
        "<div class='hero-actions'>"
        "<a class='btn' href='/runtime/reports/latest'>Latest runtime snapshot</a>"
        "<a class='btn secondary' href='/v1/exports'>Export manifest API</a>"
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
        "<section class='card'><div class='section-title'><h2>Recent exports</h2><a href='/exports'>open all</a></div>"
        f"<ul>{''.join(export_items)}</ul></section>"
        "<section class='card'><div class='section-title'><h2>Useful endpoints</h2></div>"
        f"<ul>{endpoint_rows}</ul></section>"
        "</div></div></div></body></html>"
    )


def _search_page_html(
    *,
    auth_session: FrontendAuthSession,
    workspace_names: list[str],
    initial_query: str,
    initial_scope: str,
    initial_workspace: str,
    initial_mode: str,
    initial_limit: int,
    initial_offset: int,
    initial_kind: str,
    initial_source_kind: str,
) -> str:
    options = "".join(
        f"<option value=\"{escape(name, quote=True)}\"{' selected' if name == initial_workspace else ''}>{escape(name)}</option>"
        for name in workspace_names
    )
    initial_state = json.dumps(
        {
            "query": initial_query,
            "scope": initial_scope,
            "workspace": initial_workspace,
            "mode": initial_mode,
            "limit": initial_limit,
            "offset": initial_offset,
            "kind": initial_kind,
            "source_kind": initial_source_kind,
        }
    ).replace("</", "<\\/")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Slack Mirror Search</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<style>"
        ":root{--bg:#f4efe7;--panel:#fffdf9;--ink:#122033;--muted:#5f6c7b;--line:#d9d0c3;--accent:#0b57d0;--accent-soft:#dfeafe;--ok:#1f7a44;--ok-soft:#ddefe3;--warn:#a05a00;--warn-soft:#fff0db;--bad:#a12828;--bad-soft:#fde5e5;--shadow:0 14px 30px rgba(18,32,51,.08);}"
        "*{box-sizing:border-box} body{margin:0;font-family:\"Aptos\",\"Segoe UI\",Arial,sans-serif;background:radial-gradient(circle at top right,#fff8ef 0,transparent 28%),linear-gradient(180deg,#f6f1e9 0,#efe7dc 100%);color:var(--ink)}"
        f"{_authenticated_topbar_css()}"
        "a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}"
        ".shell{max-width:1180px;margin:0 auto;padding:32px 20px 48px}.stack{display:grid;gap:18px}"
        ".card{background:var(--panel);border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:22px}"
        ".section-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px}"
        ".section-title h1,.section-title h2{margin:0}.section-title h1{font-size:34px;line-height:1.05}.section-title h2{font-size:20px}"
        ".lede{margin:0;color:var(--muted);font-size:15px;line-height:1.55;max-width:60rem}.meta{color:var(--muted);font-size:13px;line-height:1.45}"
        ".top-links,.hero-actions{display:flex;flex-wrap:wrap;gap:10px}.top-links{margin-top:16px}.hero-actions{margin-top:18px}"
        ".btn{display:inline-flex;align-items:center;gap:8px;padding:11px 14px;border-radius:14px;border:1px solid #b7c9ee;background:#edf4ff;color:var(--accent);font-weight:700}"
        ".btn.secondary{background:#f8f5ef;border-color:var(--line);color:var(--ink)}"
        ".form-grid{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:14px}.filters-grid{display:grid;grid-template-columns:1.6fr 1fr 1fr;gap:14px;margin-top:14px}"
        "label{display:block;font-size:13px;font-weight:700;margin-bottom:6px}input,select{width:100%;padding:11px 12px;border-radius:12px;border:1px solid #c8beb0;background:#fff;color:var(--ink)}"
        "input:focus,select:focus{outline:2px solid #8ab4ff;outline-offset:2px}.hint{margin-top:6px;color:var(--muted);font-size:12px}.hint.bad{color:var(--bad)}"
        ".toolbar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;margin-top:16px}.summary{color:var(--muted);font-size:13px}"
        ".results{display:grid;gap:12px;margin-top:14px}.result-card{padding:16px;border:1px solid #e4ddd1;border-radius:18px;background:#fcfaf6}.result-top{display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px;margin-bottom:10px}"
        ".result-title{font-size:16px;font-weight:800;line-height:1.3}.result-meta{display:flex;flex-wrap:wrap;gap:6px}.badge{display:inline-flex;align-items:center;padding:4px 9px;border-radius:999px;font-size:12px;font-weight:700;line-height:1}"
        ".badge-neutral{background:#ece7dc;color:#514739}.badge-ok{background:var(--ok-soft);color:var(--ok)}.badge-warn{background:var(--warn-soft);color:var(--warn)}"
        ".snippet{white-space:pre-wrap;word-break:break-word;font-size:14px;line-height:1.5;margin:0}.empty{padding:18px;border:1px dashed #d6cbbb;border-radius:16px;color:var(--muted);background:#fbf7f0}"
        ".detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0 0}.detail-item{padding:10px 12px;border-radius:14px;background:#f8f3eb;border:1px solid #e2d8ca}.detail-item .label{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}"
        ".action-row{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}.action-link{display:inline-flex;align-items:center;padding:8px 10px;border-radius:12px;border:1px solid #d4c7b6;background:#fff9f1;color:var(--ink);font-size:13px;font-weight:700}"
        ".pager{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;margin-top:16px;padding-top:12px;border-top:1px solid #e2d8ca}.pager-actions{display:flex;flex-wrap:wrap;gap:10px}"
        ".readiness{margin-top:14px;padding:14px;border-radius:16px;border:1px solid #e2d8ca;background:#f8f4ec}.readiness.hidden{display:none}.readiness-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:10px}"
        ".readiness-metric{padding:12px;border-radius:14px;background:#fffdf9;border:1px solid #e2d8ca}.readiness-metric strong{display:block;font-size:22px;line-height:1.1}"
        "code{background:#efe7da;border:1px solid #dfd3c2;padding:2px 6px;border-radius:8px;font-size:12px}"
        "@media (max-width: 900px){.form-grid,.filters-grid,.readiness-grid,.detail-grid{grid-template-columns:1fr 1fr}}"
        "@media (max-width: 640px){.shell{padding:20px 14px 32px}.section-title h1{font-size:28px}.form-grid,.filters-grid,.readiness-grid,.detail-grid{grid-template-columns:1fr}}"
        "</style></head><body><div class='shell stack'>"
        f"{_authenticated_topbar_html(auth_session=auth_session, current_path='/search')}"
        "<section class='card'>"
        "<div class='section-title'><h1>Search mirrored messages and derived text</h1></div>"
        "<p class='lede'>This browser surface stays thin over the existing corpus-search and readiness APIs, so operators can search without hand-calling JSON routes.</p>"
        "</section>"
        "<section class='card'>"
        "<div class='section-title'><h2>Search query</h2><a id='search-api-link' href='/v1/search/corpus'>JSON API</a></div>"
        "<form id='search-form'>"
        "<div class='form-grid'>"
        f"<div><label for='search-query'>Query</label><input id='search-query' name='query' value=\"{escape(initial_query, quote=True)}\" placeholder='incident review' /><div class='hint' id='search-query-help'>Searches messages plus derived attachment or OCR text from the mirrored corpus.</div></div>"
        "<div><label for='search-scope'>Scope</label><select id='search-scope' name='scope'><option value='workspace'>Selected workspace</option><option value='all'>All workspaces</option></select><div class='hint'>Use all-workspace scope sparingly for broader operator discovery.</div></div>"
        f"<div><label for='search-workspace'>Workspace</label><select id='search-workspace' name='workspace'><option value=''>Choose a workspace…</option>{options}</select><div class='hint' id='search-workspace-help'>Choose one of the mirrored workspaces available in this install.</div></div>"
        "<div><label for='search-limit'>Limit</label><select id='search-limit' name='limit'><option value='10'>10</option><option value='20'>20</option><option value='50'>50</option></select><div class='hint'>Bound large result sets in the browser for now.</div></div>"
        "</div>"
        "<div class='filters-grid'>"
        "<div><label for='search-mode'>Mode</label><select id='search-mode' name='mode'><option value='hybrid'>Hybrid</option><option value='lexical'>Lexical</option><option value='semantic'>Semantic</option></select><div class='hint'>Hybrid is the default shipped retrieval mode.</div></div>"
        "<div><label for='search-kind'>Derived text kind</label><select id='search-kind' name='kind'><option value=''>Any</option><option value='attachment_text'>Attachment text</option><option value='ocr_text'>OCR text</option></select><div class='hint'>Optional filter for non-message corpus rows.</div></div>"
        "<div><label for='search-source-kind'>Source kind</label><select id='search-source-kind' name='source_kind'><option value=''>Any</option><option value='file'>File</option><option value='canvas'>Canvas</option></select><div class='hint'>Optional filter for file vs canvas sources.</div></div>"
        "</div>"
        "<div class='toolbar'><div class='summary'>Browser route: <code>/search</code> · API routes: <code>/v1/workspaces/&lt;workspace&gt;/search/corpus</code> and <code>/v1/search/corpus</code></div><button class='btn' id='search-run-button' type='submit'>Search</button></div>"
        "<div class='hint bad' id='search-form-error' hidden></div>"
        "</form>"
        "<div class='readiness hidden' id='search-readiness-panel' aria-live='polite'></div>"
        "</section>"
        "<section class='card'>"
        "<div class='section-title'><h2>Results</h2><div class='meta' id='search-results-meta'>Enter a query to search mirrored messages and derived text.</div></div>"
        "<div class='results' id='search-results-list'><div class='empty'>Enter a query to search mirrored messages and derived text.</div></div>"
        "<div class='pager'><div class='meta' id='search-page-meta'>Page navigation appears after the first search.</div><div class='pager-actions'><button class='btn secondary' id='search-prev-button' type='button' disabled>Previous</button><button class='btn secondary' id='search-next-button' type='button' disabled>Next</button></div></div>"
        "</section>"
        f"<script>const initialSearchState={initial_state};"
        "const queryInput=document.getElementById('search-query');"
        "const scopeSelect=document.getElementById('search-scope');"
        "const workspaceSelect=document.getElementById('search-workspace');"
        "const modeSelect=document.getElementById('search-mode');"
        "const limitSelect=document.getElementById('search-limit');"
        "const kindSelect=document.getElementById('search-kind');"
        "const sourceKindSelect=document.getElementById('search-source-kind');"
        "const searchButton=document.getElementById('search-run-button');"
        "const searchError=document.getElementById('search-form-error');"
        "const searchResultsMeta=document.getElementById('search-results-meta');"
        "const searchResultsList=document.getElementById('search-results-list');"
        "const searchApiLink=document.getElementById('search-api-link');"
        "const readinessPanel=document.getElementById('search-readiness-panel');"
        "const searchPageMeta=document.getElementById('search-page-meta');"
        "const searchPrevButton=document.getElementById('search-prev-button');"
        "const searchNextButton=document.getElementById('search-next-button');"
        f"{_BROWSER_ESCAPE_HTML_JS}"
        f"{_BROWSER_BUSY_LABEL_JS}"
        f"{_BROWSER_FETCH_JSON_HELPERS_JS}"
        "function setSearchBusyState(isBusy){queryInput.disabled=isBusy;scopeSelect.disabled=isBusy;workspaceSelect.disabled=isBusy||scopeSelect.value==='all';modeSelect.disabled=isBusy;limitSelect.disabled=isBusy;kindSelect.disabled=isBusy;sourceKindSelect.disabled=isBusy;searchButton.disabled=isBusy;searchPrevButton.disabled=isBusy||searchPrevButton.disabled;searchNextButton.disabled=isBusy||searchNextButton.disabled;setButtonBusyLabel(searchButton,isBusy,'searching…');}"
        "function setSearchError(message){if(message){searchError.textContent=message;searchError.hidden=false;return;}searchError.textContent='';searchError.hidden=true;}"
        "function updateWorkspaceState(){workspaceSelect.disabled=scopeSelect.value==='all'||searchButton.disabled;}"
        "function resultScoreLabel(item){if(item._source==='hybrid'&&item._hybrid_score!==undefined)return `hybrid ${Number(item._hybrid_score).toFixed(2)}`;if(item._semantic_score!==undefined&&item._source==='semantic')return `semantic ${Number(item._semantic_score).toFixed(2)}`;if(item._score!==undefined)return `lexical ${Number(item._score).toFixed(2)}`;return item._source||'';}"
        "function resultTitle(item){if(item.result_kind==='message')return item.source_label||item.channel_name||item.channel_id||'Message hit';return item.source_label||item.source_kind||'Derived text hit';}"
        "function resultSnippet(item){const text=item.snippet_text||item.text||'';return String(text).slice(0,1200);}"
        "function buildSearchHref(state,overrides){const next={...state,...overrides};const params=stateToSearchParams(next);return params.toString()?`/search?${params.toString()}`:'/search';}"
        "function appendQueryTerm(base,term){const trimmed=(base||'').trim();const extra=(term||'').trim();if(!extra)return trimmed;if(!trimmed)return extra;return `${trimmed} ${extra}`;}"
        "function detailItem(label,value){if(value===undefined||value===null||value==='')return'';return `<div class=\"detail-item\"><span class=\"label\">${escapeHtml(label)}</span><div><code>${escapeHtml(value)}</code></div></div>`;}"
        "function resultActions(item,state){const links=[];const workspace=item.workspace||state.workspace||'';if(workspace&&state.scope==='all'){links.push(`<a class=\"action-link\" href=\"${buildSearchHref({...state,scope:'workspace',workspace,offset:0}, {})}\">workspace scope</a>`);}if(item.result_kind==='message'){const channelRef=item.channel_name||item.channel_id||'';if(workspace&&item.channel_id&&item.ts){links.push(`<a class=\"action-link\" href=\"/v1/workspaces/${encodeURIComponent(workspace)}/messages/${encodeURIComponent(item.channel_id)}/${encodeURIComponent(item.ts)}\" target=\"_blank\" rel=\"noopener\">message JSON</a>`);}if(workspace&&channelRef){links.push(`<a class=\"action-link\" href=\"${buildSearchHref({...state,scope:'workspace',workspace,offset:0},{query:appendQueryTerm(state.query,`in:${channelRef}`)})}\">channel scope</a>`);}if(item.thread_ts&&workspace&&channelRef){links.push(`<a class=\"action-link\" href=\"${buildSearchHref({...state,scope:'workspace',workspace,offset:0},{query:appendQueryTerm(state.query,`in:${channelRef} is:thread`)})}\">thread context</a>`);}}else{if(workspace&&item.source_kind&&item.source_id&&item.derivation_kind){const params=new URLSearchParams({kind:String(item.derivation_kind||'')});if(item.extractor)params.set('extractor',String(item.extractor));links.push(`<a class=\"action-link\" href=\"/v1/workspaces/${encodeURIComponent(workspace)}/derived-text/${encodeURIComponent(item.source_kind)}/${encodeURIComponent(item.source_id)}?${params.toString()}\" target=\"_blank\" rel=\"noopener\">derived text JSON</a>`);}if(workspace&&item.derivation_kind){links.push(`<a class=\"action-link\" href=\"${buildSearchHref({...state,scope:'workspace',workspace,offset:0},{kind:item.derivation_kind})}\">same kind</a>`);}if(workspace&&item.source_kind){links.push(`<a class=\"action-link\" href=\"${buildSearchHref({...state,scope:'workspace',workspace,offset:0},{source_kind:item.source_kind})}\">same source kind</a>`);}}return links.join('');}"
        "function renderEmpty(message){searchResultsMeta.textContent=message;searchResultsList.innerHTML=`<div class='empty'>${escapeHtml(message)}</div>`;}"
        "function updatePager(state,resultCount,totalCount){const limit=Math.max(1,Number(state.limit||20));const offset=Math.max(0,Number(state.offset||0));const total=Math.max(0,Number(totalCount||0));if(!state.query){searchPageMeta.textContent='No paged results yet.';searchPrevButton.disabled=true;searchNextButton.disabled=true;searchPrevButton.dataset.nextOffset='0';searchNextButton.dataset.nextOffset=String(offset+limit);return;}if(!resultCount&&!total){searchPageMeta.textContent=`No results · offset ${offset} · limit ${limit}`;searchPrevButton.disabled=offset<=0;searchNextButton.disabled=true;searchPrevButton.dataset.nextOffset=String(Math.max(0,offset-limit));searchNextButton.dataset.nextOffset=String(offset+limit);return;}const page=Math.floor(offset/limit)+1;const pageCount=Math.max(1,Math.ceil(total/limit));const start=total?offset+1:0;const end=Math.min(offset+resultCount,total||offset+resultCount);searchPageMeta.textContent=`Page ${page} of ${pageCount} · results ${start}-${end} of ${total}`;searchPrevButton.disabled=offset<=0;searchNextButton.disabled=(offset+resultCount)>=total;searchPrevButton.dataset.nextOffset=String(Math.max(0,offset-limit));searchNextButton.dataset.nextOffset=String(offset+limit);}"
        "function renderResults(results,state){if(!results.length){renderEmpty(`No results for “${state.query}”.`);return;}searchResultsMeta.textContent=`${results.length} result(s) · ${state.scope==='all'?'all workspaces':state.workspace||'selected workspace'} · ${state.mode}`;searchResultsList.innerHTML=results.map((item)=>{const workspace=item.workspace?`<code>${escapeHtml(item.workspace)}</code>`:'';const source=item._source?`<span class='badge badge-ok'>${escapeHtml(item._source)}</span>`:'';const kind=`<span class='badge badge-neutral'>${escapeHtml(item.result_kind||'result')}</span>`;const score=resultScoreLabel(item);const scoreHtml=score?`<span class='badge badge-warn'>${escapeHtml(score)}</span>`:'';const sourceKind=item.source_kind?`<code>${escapeHtml(item.source_kind)}</code>`:'';const derivedKind=item.derivation_kind?`<code>${escapeHtml(item.derivation_kind)}</code>`:'';const timestamp=item.ts||item.updated_at||item.sort_ts||'';const snippet=escapeHtml(resultSnippet(item)||'');const details=item.result_kind==='message'?[detailItem('channel',item.channel_name||item.channel_id||''),detailItem('timestamp',item.ts||''),detailItem('user',item.user_id||''),detailItem('thread',item.thread_ts||'')].join(''):[detailItem('source id',item.source_id||''),detailItem('updated',item.updated_at||''),detailItem('extractor',item.extractor||''),detailItem('local path',item.local_path||'')].join('');const actions=resultActions(item,state);return `<article class=\"result-card\"><div class=\"result-top\"><div><div class=\"result-title\">${escapeHtml(resultTitle(item))}</div><div class=\"result-meta\">${kind}${source}${scoreHtml}${workspace}${sourceKind}${derivedKind}</div></div><div class=\"meta\">${escapeHtml(timestamp)}</div></div><p class=\"snippet\">${snippet||'No snippet available.'}</p>${details?`<div class=\"detail-grid\">${details}</div>`:''}${actions?`<div class=\"action-row\">${actions}</div>`:''}</article>`;}).join('');}"
        "function renderReadiness(payload,workspace){if(!payload){readinessPanel.classList.add('hidden');readinessPanel.innerHTML='';return;}const messages=payload.messages||{};const embeddings=messages.embeddings||{};const derived=payload.derived_text||{};const attachment=derived.attachment_text||{};const ocr=derived.ocr_text||{};readinessPanel.classList.remove('hidden');readinessPanel.innerHTML=`<div><strong>Workspace readiness</strong> <code>${escapeHtml(workspace)}</code> <span class=\"badge ${payload.status==='ready'?'badge-ok':'badge-warn'}\">${escapeHtml(payload.status||'unknown')}</span></div><div class=\"meta\">Use this to distinguish weak results from a corpus that is still catching up on embeddings or derived text.</div><div class=\"readiness-grid\"><div class=\"readiness-metric\"><span class=\"meta\">Messages</span><strong>${Number(messages.count||0)}</strong><div class=\"meta\">embeddings ${Number(embeddings.count||0)} · pending ${Number(embeddings.pending||0)} · errors ${Number(embeddings.errors||0)}</div></div><div class=\"readiness-metric\"><span class=\"meta\">Attachment text</span><strong>${Number(attachment.count||0)}</strong><div class=\"meta\">pending ${Number(attachment.pending||0)} · errors ${Number(attachment.errors||0)}</div></div><div class=\"readiness-metric\"><span class=\"meta\">OCR text</span><strong>${Number(ocr.count||0)}</strong><div class=\"meta\">pending ${Number(ocr.pending||0)} · errors ${Number(ocr.errors||0)}</div></div></div>`;}"
        "function currentState(){return {query:queryInput.value.trim(),scope:scopeSelect.value,workspace:workspaceSelect.value.trim(),mode:modeSelect.value,limit:limitSelect.value,offset:Number(initialSearchState.offset||0),kind:kindSelect.value,source_kind:sourceKindSelect.value};}"
        "function stateToSearchParams(state){const params=new URLSearchParams();if(state.query)params.set('query',state.query);if(state.scope&&state.scope!=='workspace')params.set('scope',state.scope);if(state.workspace)params.set('workspace',state.workspace);if(state.mode&&state.mode!=='hybrid')params.set('mode',state.mode);if(state.limit&&String(state.limit)!=='20')params.set('limit',String(state.limit));if(Number(state.offset||0)>0)params.set('offset',String(state.offset));if(state.kind)params.set('kind',state.kind);if(state.source_kind)params.set('source_kind',state.source_kind);return params;}"
        "function updateUrlAndApiLink(state){const params=stateToSearchParams(state);const nextUrl=params.toString()?`/search?${params.toString()}`:'/search';window.history.replaceState(null,'',nextUrl);const apiParams=new URLSearchParams();if(state.query)apiParams.set('query',state.query);apiParams.set('mode',state.mode||'hybrid');apiParams.set('limit',String(state.limit||20));if(Number(state.offset||0)>0)apiParams.set('offset',String(state.offset));if(state.kind)apiParams.set('kind',state.kind);if(state.source_kind)apiParams.set('source_kind',state.source_kind);const href=state.scope==='all'?`/v1/search/corpus?${apiParams.toString()}`:`/v1/workspaces/${encodeURIComponent(state.workspace||'')}/search/corpus?${apiParams.toString()}`;searchApiLink.setAttribute('href',href);}"
        "async function loadReadiness(state){if(state.scope==='all'||!state.workspace){renderReadiness(null,'');return;}const {resp,data}=await fetchJsonResponse(`/v1/workspaces/${encodeURIComponent(state.workspace)}/search/readiness`);if(!resp.ok){renderReadiness({status:'degraded',messages:{},derived_text:{}},state.workspace);const meta=readinessPanel.querySelector('.meta');if(meta)meta.textContent=responseErrorMessage(data,'Failed to load readiness');return;}renderReadiness(data?.readiness||null,state.workspace);}"
        "async function runSearch(state){setSearchError('');updateWorkspaceState();updateUrlAndApiLink(state);if(!state.query){renderEmpty('Enter a query to search mirrored messages and derived text.');updatePager(state,0,0);renderReadiness(null,'');return;}if(state.scope!=='all'&&!state.workspace){setSearchError('Workspace is required unless searching all workspaces.');renderEmpty('Choose a workspace or switch to all-workspace search.');updatePager(state,0,0);renderReadiness(null,'');return;}setSearchBusyState(true);searchResultsMeta.textContent='Running search…';searchResultsList.innerHTML='<div class=\"empty\">Running search…</div>';searchPageMeta.textContent='Running search…';try{const params=new URLSearchParams({query:state.query,mode:state.mode||'hybrid',limit:String(state.limit||20),offset:String(state.offset||0)});if(state.kind)params.set('kind',state.kind);if(state.source_kind)params.set('source_kind',state.source_kind);const href=state.scope==='all'?`/v1/search/corpus?${params.toString()}`:`/v1/workspaces/${encodeURIComponent(state.workspace)}/search/corpus?${params.toString()}`;const {resp,data}=await fetchJsonResponse(href);if(!resp.ok){const message=responseErrorMessage(data,'Search failed');setSearchError(message);renderEmpty(message);updatePager(state,0,0);renderReadiness(null,'');return;}const results=data?.results||[];const nextState={...(state),offset:Number(data?.offset??state.offset??0),limit:Number(data?.limit??state.limit??20)};const total=Number(data?.total??results.length);renderResults(results,nextState);updatePager(nextState,results.length,total);await loadReadiness(nextState);}finally{setSearchBusyState(false);updateWorkspaceState();}}"
        "scopeSelect.addEventListener('change',()=>{setSearchError('');updateWorkspaceState();if(scopeSelect.value==='all')readinessPanel.classList.add('hidden');});"
        "workspaceSelect.addEventListener('change',()=>setSearchError(''));queryInput.addEventListener('input',()=>setSearchError(''));"
        "document.getElementById('search-form').addEventListener('submit',async(event)=>{event.preventDefault();const state=currentState();state.offset=0;initialSearchState.offset=0;await runSearch(state);});"
        "searchPrevButton.addEventListener('click',async()=>{const state=currentState();state.offset=Number(searchPrevButton.dataset.nextOffset||0);initialSearchState.offset=state.offset;await runSearch(state);});"
        "searchNextButton.addEventListener('click',async()=>{const state=currentState();state.offset=Number(searchNextButton.dataset.nextOffset||0);initialSearchState.offset=state.offset;await runSearch(state);});"
        "scopeSelect.value=initialSearchState.scope==='all'?'all':'workspace';workspaceSelect.value=initialSearchState.workspace||workspaceSelect.value;modeSelect.value=initialSearchState.mode||'hybrid';limitSelect.value=String(initialSearchState.limit||20);kindSelect.value=initialSearchState.kind||'';sourceKindSelect.value=initialSearchState.source_kind||'';updateWorkspaceState();updateUrlAndApiLink(currentState());updatePager(currentState(),0,0);if(initialSearchState.query){runSearch(currentState());}"
        "</script></div></body></html>"
    )


def _logs_page_html(
    *,
    auth_session: FrontendAuthSession,
    tenant_names: list[str],
    initial_tenant: str,
    initial_source: str,
    initial_limit: int,
) -> str:
    options = "".join(
        f"<option value=\"{escape(name, quote=True)}\"{' selected' if name == initial_tenant else ''}>{escape(name)}</option>"
        for name in tenant_names
    )
    initial_state = json.dumps(
        {
            "tenant": initial_tenant,
            "source": initial_source,
            "limit": initial_limit,
        }
    ).replace("</", "<\\/")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Slack Mirror Logs</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<style>"
        ":root{--bg:#f4efe7;--panel:#fffdf9;--ink:#122033;--muted:#5f6c7b;--line:#d9d0c3;--accent:#0b57d0;--accent-soft:#dfeafe;--ok:#1f7a44;--ok-soft:#ddefe3;--warn:#a05a00;--warn-soft:#fff0db;--bad:#a12828;--bad-soft:#fde5e5;--shadow:0 14px 30px rgba(18,32,51,.08);}"
        "*{box-sizing:border-box} body{margin:0;font-family:\"Aptos\",\"Segoe UI\",Arial,sans-serif;background:radial-gradient(circle at top right,#fff8ef 0,transparent 28%),linear-gradient(180deg,#f6f1e9 0,#efe7dc 100%);color:var(--ink)}"
        f"{_authenticated_topbar_css()}"
        ".shell{max-width:1220px;margin:0 auto;padding:32px 20px 48px}.stack{display:grid;gap:18px}"
        ".card{background:var(--panel);border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:22px}"
        ".section-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px}"
        ".section-title h1,.section-title h2{margin:0}.section-title h1{font-size:34px;line-height:1.05}.section-title h2{font-size:20px}"
        ".lede{margin:0;color:var(--muted);font-size:15px;line-height:1.55;max-width:64rem}.meta{color:var(--muted);font-size:13px;line-height:1.45}"
        ".form-grid{display:grid;grid-template-columns:1.2fr 1fr .55fr auto;gap:14px;align-items:end}"
        "label{display:block;font-size:13px;font-weight:700;margin-bottom:6px}select,input{width:100%;padding:11px 12px;border-radius:12px;border:1px solid #c8beb0;background:#fff;color:var(--ink)}"
        "select:focus,input:focus{outline:2px solid #8ab4ff;outline-offset:2px}.hint{margin-top:6px;color:var(--muted);font-size:12px}.hint.bad{color:var(--bad)}"
        ".toolbar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;margin-top:16px}"
        ".btn{display:inline-flex;align-items:center;gap:8px;padding:11px 14px;border-radius:14px;border:1px solid #b7c9ee;background:#edf4ff;color:var(--accent);font-weight:700;cursor:pointer}"
        ".btn.secondary{background:#f8f5ef;border-color:var(--line);color:var(--ink)}"
        ".toggle-row{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:13px}.toggle-row input{width:16px;height:16px}"
        ".status-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.status-pill{display:inline-flex;align-items:center;padding:5px 9px;border-radius:999px;font-size:12px;font-weight:700;background:#ebe4d8;color:#514739}"
        ".status-pill.ok{background:var(--ok-soft);color:var(--ok)}.status-pill.warn{background:var(--warn-soft);color:var(--warn)}.status-pill.bad{background:var(--bad-soft);color:var(--bad)}"
        ".empty{padding:18px;border:1px dashed #d6cbbb;border-radius:16px;color:var(--muted);background:#fbf7f0}"
        ".viewer-head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}"
        ".viewer-meta{display:grid;gap:4px}.log-output{margin:0;padding:18px;border-radius:18px;border:1px solid #d8cdc0;background:#171717;color:#f5f5f5;overflow:auto;max-height:68vh;white-space:pre-wrap;word-break:break-word;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}"
        "@media (max-width: 900px){.form-grid{grid-template-columns:1fr 1fr}.viewer-head{align-items:flex-start}}"
        "@media (max-width: 640px){.shell{padding:20px 14px 32px}.section-title h1{font-size:28px}.form-grid{grid-template-columns:1fr}}"
        "</style></head><body><div class='shell stack'>"
        f"{_authenticated_topbar_html(auth_session=auth_session, current_path='/logs')}"
        "<section class='card'>"
        "<div class='section-title'><h1>Tenant and service logs</h1></div>"
        "<p class='lede'>Use this page to inspect bounded <code>journalctl --user</code> output for tenant live units and the shared managed services. This is a poll-first operator view, not a streaming tail.</p>"
        "</section>"
        "<section class='card'>"
        "<div class='section-title'><h2>Log source</h2><a id='logs-api-link' href='/v1/logs'>JSON API</a></div>"
        "<form id='logs-form'>"
        "<div class='form-grid'>"
        "<div><label for='logs-source'>Source</label><select id='logs-source' name='source'>"
        "<option value='tenant_all'>Tenant live units</option>"
        "<option value='webhooks'>Tenant webhooks unit</option>"
        "<option value='daemon'>Tenant daemon unit</option>"
        "<option value='api'>Managed API service</option>"
        "<option value='runtime-report'>Runtime report service</option>"
        "</select><div class='hint'>Tenant selections map to the same systemd unit names used by the live-ops runbook.</div></div>"
        f"<div><label for='logs-tenant'>Tenant</label><select id='logs-tenant' name='tenant'><option value=''>Choose a tenant…</option>{options}</select><div class='hint' id='logs-tenant-help'>Required for tenant unit views; ignored for shared managed services.</div></div>"
        "<div><label for='logs-limit'>Lines</label><select id='logs-limit' name='limit'><option value='50'>50</option><option value='100'>100</option><option value='200'>200</option><option value='400'>400</option></select><div class='hint'>Bound browser payload size.</div></div>"
        "<div><button class='btn' id='logs-refresh-button' type='submit'>Refresh logs</button></div>"
        "</div>"
        "<div class='toolbar'><div class='meta'>Browser route: <code>/logs</code> · JSON route: <code>/v1/logs</code></div><label class='toggle-row'><input id='logs-auto-refresh' type='checkbox' /> auto refresh every 5 seconds</label></div>"
        "<div class='hint bad' id='logs-form-error' hidden></div>"
        "</form>"
        "<div class='status-row' id='logs-status-row'><span class='status-pill'>Waiting for selection</span></div>"
        "</section>"
        "<section class='card'>"
        "<div class='viewer-head'><div class='viewer-meta'><strong id='logs-viewer-title'>No logs loaded</strong><div class='meta' id='logs-viewer-meta'>Choose a source and refresh.</div></div><div class='meta' id='logs-viewer-command'></div></div>"
        "<pre class='log-output' id='logs-output'>Choose a source and refresh.</pre>"
        "</section>"
        f"<script>const initialLogsState={initial_state};"
        "const sourceSelect=document.getElementById('logs-source');"
        "const tenantSelect=document.getElementById('logs-tenant');"
        "const limitSelect=document.getElementById('logs-limit');"
        "const refreshButton=document.getElementById('logs-refresh-button');"
        "const autoRefreshCheckbox=document.getElementById('logs-auto-refresh');"
        "const formError=document.getElementById('logs-form-error');"
        "const statusRow=document.getElementById('logs-status-row');"
        "const viewerTitle=document.getElementById('logs-viewer-title');"
        "const viewerMeta=document.getElementById('logs-viewer-meta');"
        "const viewerCommand=document.getElementById('logs-viewer-command');"
        "const output=document.getElementById('logs-output');"
        "const apiLink=document.getElementById('logs-api-link');"
        "let logsPollHandle=null;"
        f"{_BROWSER_ESCAPE_HTML_JS}"
        f"{_BROWSER_BUSY_LABEL_JS}"
        f"{_BROWSER_FETCH_JSON_HELPERS_JS}"
        "function currentLogsState(){return {source:sourceSelect.value,tenant:tenantSelect.value.trim(),limit:Number(limitSelect.value||100)};}"
        "function logsNeedsTenant(source){return source==='tenant_all'||source==='webhooks'||source==='daemon';}"
        "function updateLogsFormState(){const requiresTenant=logsNeedsTenant(sourceSelect.value);tenantSelect.disabled=!requiresTenant||refreshButton.disabled;const help=document.getElementById('logs-tenant-help');if(help)help.textContent=requiresTenant?'Required for the selected tenant unit view.':'Ignored for the selected shared managed service.';}"
        "function setLogsBusyState(isBusy){sourceSelect.disabled=isBusy;limitSelect.disabled=isBusy;refreshButton.disabled=isBusy;setButtonBusyLabel(refreshButton,isBusy,'loading…');updateLogsFormState();}"
        "function setLogsError(message){if(message){formError.textContent=message;formError.hidden=false;return;}formError.textContent='';formError.hidden=true;}"
        "function updateLogsApiLink(state){const params=new URLSearchParams({source:state.source,limit:String(state.limit)});if(state.tenant)params.set('tenant',state.tenant);apiLink.setAttribute('href',`/v1/logs?${params.toString()}`);const browserParams=new URLSearchParams();if(state.source!=='tenant_all')browserParams.set('source',state.source);if(state.tenant)browserParams.set('tenant',state.tenant);if(Number(state.limit)!==100)browserParams.set('limit',String(state.limit));const nextUrl=browserParams.toString()?`/logs?${browserParams.toString()}`:'/logs';window.history.replaceState(null,'',nextUrl);}"
        "function renderLogsStatus(payload){const pills=[];const units=(payload?.units||[]).map((unit)=>`<span class='status-pill'>${escapeHtml(unit)}</span>`).join('');if(payload?.ok===false){statusRow.innerHTML='<span class=\"status-pill bad\">error</span>';return;}pills.push(`<span class=\"status-pill ok\">${escapeHtml(String(payload?.source_label||'logs'))}</span>`);pills.push(`<span class=\"status-pill\">${Number(payload?.line_count||0)} lines</span>`);if(payload?.truncated)pills.push('<span class=\"status-pill warn\">bounded</span>');statusRow.innerHTML=pills.join('')+(units?` ${units}`:'');}"
        "function renderLogsPayload(payload){renderLogsStatus(payload);viewerTitle.textContent=String(payload?.source_label||'Logs');viewerMeta.textContent=`Fetched ${String(payload?.fetched_at||'')} · ${Number(payload?.line_count||0)} lines`;viewerCommand.innerHTML=payload?.command?`<code>${escapeHtml(String(payload.command))}</code>`:'';const lines=Array.isArray(payload?.lines)?payload.lines:[];output.textContent=lines.length?lines.join('\\n'):'No journal lines returned for this selection.';}"
        "async function loadLogs(){const state=currentLogsState();updateLogsApiLink(state);setLogsError('');if(logsNeedsTenant(state.source)&&!state.tenant){setLogsError('Tenant is required for tenant-unit logs.');renderLogsStatus({ok:false});viewerTitle.textContent='No logs loaded';viewerMeta.textContent='Choose a tenant and refresh.';viewerCommand.textContent='';output.textContent='Choose a tenant and refresh.';return;}setLogsBusyState(true);try{const params=new URLSearchParams({source:state.source,limit:String(state.limit)});if(state.tenant)params.set('tenant',state.tenant);const {resp,data}=await fetchJsonResponse(`/v1/logs?${params.toString()}`);if(!resp.ok){const message=responseErrorMessage(data,'Log fetch failed');setLogsError(message);renderLogsStatus({ok:false});viewerTitle.textContent='Log fetch failed';viewerMeta.textContent=message;viewerCommand.textContent='';output.textContent=message;return;}renderLogsPayload(data);}finally{setLogsBusyState(false);}}"
        "function syncAutoRefresh(){if(logsPollHandle){window.clearInterval(logsPollHandle);logsPollHandle=null;}if(autoRefreshCheckbox.checked){logsPollHandle=window.setInterval(()=>{loadLogs().catch(()=>{});},5000);}}"
        "sourceSelect.addEventListener('change',()=>{setLogsError('');updateLogsFormState();updateLogsApiLink(currentLogsState());});"
        "tenantSelect.addEventListener('change',()=>{setLogsError('');updateLogsApiLink(currentLogsState());});"
        "limitSelect.addEventListener('change',()=>updateLogsApiLink(currentLogsState()));"
        "autoRefreshCheckbox.addEventListener('change',syncAutoRefresh);"
        "document.getElementById('logs-form').addEventListener('submit',async(event)=>{event.preventDefault();await loadLogs();});"
        "sourceSelect.value=initialLogsState.source||'tenant_all';tenantSelect.value=initialLogsState.tenant||tenantSelect.value;limitSelect.value=String(initialLogsState.limit||100);updateLogsFormState();updateLogsApiLink(currentLogsState());if(initialLogsState.tenant||!logsNeedsTenant(initialLogsState.source||'tenant_all')){loadLogs();}"
        "</script></div></body></html>"
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


def _safe_log_limit(value: Any) -> int:
    try:
        limit = int(value or 100)
    except (TypeError, ValueError):
        limit = 100
    return max(10, min(limit, 400))


def _log_source_label(*, source: str, tenant: str | None) -> str:
    if source == "api":
        return "Managed API service"
    if source == "runtime-report":
        return "Runtime report service"
    if source == "webhooks":
        return f"Tenant {tenant} webhooks"
    if source == "daemon":
        return f"Tenant {tenant} daemon"
    return f"Tenant {tenant} live units"


def _log_units_for_request(*, source: str, tenant: str | None) -> list[str]:
    normalized_source = str(source or "tenant_all").strip().lower()
    if normalized_source == "api":
        return ["slack-mirror-api.service"]
    if normalized_source == "runtime-report":
        return ["slack-mirror-runtime-report.service"]
    if normalized_source not in {"tenant_all", "webhooks", "daemon"}:
        raise ValueError("unknown log source")
    if not tenant:
        raise ValueError("tenant is required for tenant log sources")
    from slack_mirror.service.tenant_onboarding import _tenant_live_units, normalize_tenant_name

    webhooks_unit, daemon_unit = _tenant_live_units(normalize_tenant_name(tenant))
    if normalized_source == "webhooks":
        return [webhooks_unit]
    if normalized_source == "daemon":
        return [daemon_unit]
    return [webhooks_unit, daemon_unit]


def _read_user_journal(*, units: list[str], limit: int) -> dict[str, Any]:
    if not units:
        raise ValueError("at least one unit is required")
    command = ["journalctl", "--user", "--no-pager", "-o", "short-iso", "-n", str(limit)]
    for unit in units:
        command.extend(["-u", unit])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    stdout = result.stdout or ""
    stderr = (result.stderr or "").strip()
    if result.returncode != 0 and not stdout.strip():
        raise RuntimeError(stderr or f"journalctl failed with exit status {result.returncode}")
    lines = stdout.splitlines()
    return {
        "command": " ".join(command),
        "lines": lines,
        "line_count": len(lines),
        "stderr": stderr,
        "returncode": result.returncode,
        "truncated": len(lines) >= limit,
    }


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
            if path in {"/", "/settings", "/settings/tenants", "/search", "/logs"}:
                return True
            if path.startswith("/v1/workspaces/") and path.endswith("/webhook"):
                return False
            protected_prefixes = (
                "/exports",
                "/v1/exports",
                "/v1/logs",
                "/v1/workspaces",
                "/runtime/reports",
                "/v1/runtime/reports",
                "/v1/runtime/status",
                "/v1/runtime/live-validation",
                "/v1/tenants",
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
            destination = _login_path(next_path=self._request_path_with_query(), reason="auth_required")
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
                reason = str(query.get("reason", [""])[0] or "").strip() or None
                if auth_session.authenticated:
                    _redirect_response(self, next_path)
                    return
                _html_response(
                    self,
                    200,
                    _frontend_login_html(
                        next_path=next_path,
                        error=error,
                        reason=reason,
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
                self.send_header("location", _login_path(next_path="/", reason="signed_out"))
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

            if path == "/settings/tenants":
                from slack_mirror.service.tenant_onboarding import tenant_status

                try:
                    tenants = tenant_status(config_path=config_path)
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="tenants.status")
                    return
                _html_response(self, 200, _tenant_settings_html(auth_session=auth_session, tenants=tenants))
                return

            if path == "/v1/tenants":
                from slack_mirror.service.tenant_onboarding import tenant_status

                try:
                    tenants = tenant_status(config_path=config_path)
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="tenants.status")
                    return
                _json_response(self, 200, {"ok": True, "tenants": tenants})
                return

            if path == "/logs":
                from slack_mirror.service.tenant_onboarding import tenant_status

                try:
                    tenants = tenant_status(config_path=config_path)
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="logs.tenants")
                    return
                tenant_names = sorted(str(item.get("name") or "").strip() for item in tenants if str(item.get("name") or "").strip())
                initial_source = str(query.get("source", ["tenant_all"])[0] or "tenant_all").strip().lower()
                if initial_source not in {"tenant_all", "webhooks", "daemon", "api", "runtime-report"}:
                    initial_source = "tenant_all"
                requested_tenant = str(query.get("tenant", [""])[0] or "").strip()
                initial_tenant = requested_tenant if requested_tenant in tenant_names else (tenant_names[0] if tenant_names else "")
                initial_limit = _safe_log_limit(query.get("limit", [100])[0] if "limit" in query else 100)
                _html_response(
                    self,
                    200,
                    _logs_page_html(
                        auth_session=auth_session,
                        tenant_names=tenant_names,
                        initial_tenant=initial_tenant,
                        initial_source=initial_source,
                        initial_limit=initial_limit,
                    ),
                )
                return

            if path == "/v1/logs":
                from slack_mirror.service.tenant_onboarding import tenant_status

                source = str(query.get("source", ["tenant_all"])[0] or "tenant_all").strip().lower()
                tenant = str(query.get("tenant", [""])[0] or "").strip()
                limit = _safe_log_limit(query.get("limit", [100])[0] if "limit" in query else 100)
                try:
                    tenants = tenant_status(config_path=config_path)
                    tenant_names = {str(item.get("name") or "").strip() for item in tenants if str(item.get("name") or "").strip()}
                    if source in {"tenant_all", "webhooks", "daemon"}:
                        if not tenant:
                            raise ValueError("tenant is required for tenant log sources")
                        if tenant not in tenant_names:
                            raise ValueError(f"unknown tenant: {tenant}")
                    units = _log_units_for_request(source=source, tenant=tenant or None)
                    payload = _read_user_journal(units=units, limit=limit)
                except ValueError as exc:
                    _error_response(self, 400, "INVALID_LOG_REQUEST", str(exc))
                    return
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="logs.read", tenant=tenant or None, source=source)
                    return
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "source": source,
                        "tenant": tenant or None,
                        "source_label": _log_source_label(source=source, tenant=tenant or None),
                        "units": units,
                        "limit": limit,
                        "command": payload["command"],
                        "lines": payload["lines"],
                        "line_count": payload["line_count"],
                        "truncated": payload["truncated"],
                        "stderr": payload["stderr"],
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                return

            m = re.fullmatch(r"/v1/tenants/([^/]+)/manifest", path)
            if m:
                from slack_mirror.service.tenant_onboarding import read_tenant_manifest

                tenant_name = unquote(m.group(1))
                try:
                    payload = read_tenant_manifest(config_path=config_path, name=tenant_name)
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="tenants.manifest")
                    return
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "tenant": payload["tenant"],
                        "manifest_path": payload["manifest_path"],
                        "content": payload["content"],
                    },
                )
                return

            if path == "/search":
                conn = service.connect()
                workspace_rows = service.list_workspaces(conn)
                workspace_names = [str(item.get("name") or "").strip() for item in workspace_rows if str(item.get("name") or "").strip()]
                if not workspace_names:
                    workspace_names = [name for name in service.enabled_workspace_names() if name]
                initial_scope = "all" if str(query.get("scope", ["workspace"])[0] or "workspace").strip().lower() == "all" else "workspace"
                requested_workspace = str(query.get("workspace", [""])[0] or "").strip()
                initial_workspace = requested_workspace if requested_workspace in workspace_names else (workspace_names[0] if workspace_names else "")
                initial_mode = str(query.get("mode", ["hybrid"])[0] or "hybrid").strip().lower()
                if initial_mode not in {"hybrid", "lexical", "semantic"}:
                    initial_mode = "hybrid"
                initial_limit = int(query.get("limit", [20])[0] or 20)
                if initial_limit not in {10, 20, 50}:
                    initial_limit = 20
                initial_offset = max(0, int(query.get("offset", [0])[0] or 0))
                initial_kind = str(query.get("kind", [""])[0] or "").strip()
                if initial_kind not in {"", "attachment_text", "ocr_text"}:
                    initial_kind = ""
                initial_source_kind = str(query.get("source_kind", [""])[0] or "").strip()
                if initial_source_kind not in {"", "file", "canvas"}:
                    initial_source_kind = ""
                _html_response(
                    self,
                    200,
                    _search_page_html(
                        auth_session=auth_session,
                        workspace_names=workspace_names,
                        initial_query=str(query.get("query", [""])[0] or "").strip(),
                        initial_scope=initial_scope,
                        initial_workspace=initial_workspace,
                        initial_mode=initial_mode,
                        initial_limit=initial_limit,
                        initial_offset=initial_offset,
                        initial_kind=initial_kind,
                        initial_source_kind=initial_source_kind,
                    ),
                )
                return

            if path == "/v1/workspaces":
                conn = service.connect()
                _json_response(self, 200, {"ok": True, "workspaces": service.list_workspaces(conn)})
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/channels", path)
            if m:
                conn = service.connect()
                try:
                    payload = service.list_workspace_channels(conn, workspace=m.group(1))
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, workspace=m.group(1), operation="workspaces.channels.list")
                    return
                _json_response(self, 200, {"ok": True, "channels": payload})
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/messages/([^/]+)/([^/]+)", path)
            if m:
                conn = service.connect()
                workspace = unquote(m.group(1))
                channel_id = unquote(m.group(2))
                ts = unquote(m.group(3))
                try:
                    payload = service.get_message_detail(
                        conn,
                        workspace=workspace,
                        channel_id=channel_id,
                        ts=ts,
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(
                        self,
                        exc,
                        path=path,
                        workspace=workspace,
                        channel_id=channel_id,
                        ts=ts,
                        operation="messages.detail",
                    )
                    return
                if payload is None:
                    _error_response(self, 404, "NOT_FOUND", f"Message not found: {workspace}/{channel_id}/{ts}")
                    return
                _json_response(self, 200, {"ok": True, "message": payload})
                return

            m = re.fullmatch(r"/v1/workspaces/([^/]+)/derived-text/([^/]+)/([^/]+)", path)
            if m:
                conn = service.connect()
                workspace = unquote(m.group(1))
                source_kind = unquote(m.group(2))
                source_id = unquote(m.group(3))
                derivation_kind = str(query.get("kind", [""])[0] or "").strip()
                extractor = str(query.get("extractor", [""])[0] or "").strip() or None
                if not derivation_kind:
                    _error_response(self, 400, "BAD_REQUEST", "kind query parameter is required")
                    return
                try:
                    payload = service.get_derived_text_detail(
                        conn,
                        workspace=workspace,
                        source_kind=source_kind,
                        source_id=source_id,
                        derivation_kind=derivation_kind,
                        extractor=extractor,
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(
                        self,
                        exc,
                        path=path,
                        workspace=workspace,
                        source_kind=source_kind,
                        source_id=source_id,
                        derivation_kind=derivation_kind,
                        operation="derived_text.detail",
                    )
                    return
                if payload is None:
                    _error_response(
                        self,
                        404,
                        "NOT_FOUND",
                        f"Derived text not found: {workspace}/{source_kind}/{source_id}/{derivation_kind}",
                    )
                    return
                _json_response(self, 200, {"ok": True, "derived_text": payload})
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
                _html_response(
                    self,
                    200,
                    _runtime_reports_index_html(
                        reports,
                        auth_session=auth_session,
                        base_url_choices=payload.base_url_choices,
                    ),
                )
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

            if path == "/exports":
                audience = str(query.get("audience", ["local"])[0])
                payload = list_export_manifests(export_root, base_urls=export_base_urls, default_audience=audience)
                _html_response(self, 200, _exports_index_html(payload))
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
                    payload = service.corpus_search_page(
                        conn,
                        workspace=m.group(1),
                        query=str(query.get("query", [""])[0]),
                        limit=int(query.get("limit", [20])[0]),
                        offset=int(query.get("offset", [0])[0]),
                        mode=str(query.get("mode", ["hybrid"])[0]),
                        model_id=str(query.get("model", ["local-hash-128"])[0]),
                        lexical_weight=float(query.get("lexical_weight", [0.6])[0]),
                        semantic_weight=float(query.get("semantic_weight", [0.4])[0]),
                        semantic_scale=float(query.get("semantic_scale", [10.0])[0]),
                        use_fts=query.get("no_fts", ["0"])[0] not in {"1", "true", "yes"},
                        derived_kind=query.get("kind", [None])[0],
                        derived_source_kind=query.get("source_kind", [None])[0],
                        rerank=query.get("rerank", ["0"])[0] in {"1", "true", "yes"},
                        rerank_top_n=int(query.get("rerank_top_n", [50])[0]),
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, workspace=m.group(1), operation="search.corpus")
                    return
                _json_response(
                    self,
                    200,
                    {"ok": True, **payload},
                )
                return

            if path == "/v1/search/corpus":
                conn = service.connect()
                try:
                    payload = service.corpus_search_page(
                        conn,
                        all_workspaces=True,
                        query=str(query.get("query", [""])[0]),
                        limit=int(query.get("limit", [20])[0]),
                        offset=int(query.get("offset", [0])[0]),
                        mode=str(query.get("mode", ["hybrid"])[0]),
                        model_id=str(query.get("model", ["local-hash-128"])[0]),
                        lexical_weight=float(query.get("lexical_weight", [0.6])[0]),
                        semantic_weight=float(query.get("semantic_weight", [0.4])[0]),
                        semantic_scale=float(query.get("semantic_scale", [10.0])[0]),
                        use_fts=query.get("no_fts", ["0"])[0] not in {"1", "true", "yes"},
                        derived_kind=query.get("kind", [None])[0],
                        derived_source_kind=query.get("source_kind", [None])[0],
                        rerank=query.get("rerank", ["0"])[0] in {"1", "true", "yes"},
                        rerank_top_n=int(query.get("rerank_top_n", [50])[0]),
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="search.corpus")
                    return
                _json_response(
                    self,
                    200,
                    {"ok": True, "scope": "all", **payload},
                )
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

            if _requires_same_origin_write(path):
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
                        remote_addr=self.client_address[0] if self.client_address else None,
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

            if path == "/v1/runtime/reports":
                try:
                    payload = service.create_runtime_report(
                        base_url=str(body.get("base_url") or "http://slack.localhost"),
                        name=str(body.get("name") or "runtime-report"),
                        timeout=float(body.get("timeout") or 5.0),
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="runtime.reports.create")
                    return
                _json_response(self, 201, {"ok": True, "report": {**payload, **runtime_report_links(str(payload.get('name') or ''))}})
                return

            m = re.fullmatch(r"/v1/runtime/reports/([^/]+)/rename", path)
            if m:
                try:
                    payload = service.rename_runtime_report(
                        name=m.group(1),
                        new_name=str(body.get("name") or ""),
                    )
                except FileNotFoundError:
                    _error_response(self, 404, "NOT_FOUND", f"Runtime report not found: {m.group(1)}")
                    return
                except FileExistsError:
                    _error_response(self, 409, "CONFLICT", f"Runtime report already exists: {body.get('name')}")
                    return
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="runtime.reports.rename")
                    return
                _json_response(self, 200, {"ok": True, "report": {**payload, **runtime_report_links(str(payload.get('name') or ''))}})
                return

            if path == "/v1/exports":
                kind = str(body.get("kind") or "channel-day")
                if kind != "channel-day":
                    _error_response(self, 400, "BAD_REQUEST", f"Unsupported export kind: {kind}")
                    return
                try:
                    payload = service.create_channel_day_export(
                        workspace=str(body.get("workspace") or ""),
                        channel=str(body.get("channel") or ""),
                        day=str(body.get("day") or ""),
                        tz=str(body.get("tz") or "America/Chicago"),
                        audience=str(body.get("audience") or "local"),
                        export_id=str(body.get("export_id") or "") or None,
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="exports.create")
                    return
                _json_response(self, 201, {"ok": True, "export": payload})
                return

            if path == "/v1/tenants/onboard":
                from slack_mirror.service.tenant_onboarding import scaffold_tenant

                try:
                    result = scaffold_tenant(
                        config_path=config_path,
                        name=str(body.get("name") or ""),
                        domain=str(body.get("domain") or ""),
                        display_name=str(body.get("display_name") or "") or None,
                        manifest_path=str(body.get("manifest_path") or "") or None,
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="tenants.onboard")
                    return
                _json_response(
                    self,
                    201,
                    {
                        "ok": True,
                        "changed": result.changed,
                        "config_path": result.config_path,
                        "backup_path": result.backup_path,
                        "manifest_path": result.manifest_path,
                        "tenant": result.tenant,
                    },
                )
                return

            m = re.fullmatch(r"/v1/tenants/([^/]+)/credentials", path)
            if m:
                from slack_mirror.service.tenant_onboarding import install_tenant_credentials

                tenant_name = unquote(m.group(1))
                try:
                    result = install_tenant_credentials(
                        config_path=config_path,
                        name=tenant_name,
                        credentials=dict(body.get("credentials") or {}),
                        dry_run=bool(body.get("dry_run", False)),
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="tenants.credentials")
                    return
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "changed": result.changed,
                        "dry_run": result.dry_run,
                        "dotenv_path": result.dotenv_path,
                        "backup_path": result.backup_path,
                        "installed_keys": result.installed_keys,
                        "skipped_keys": result.skipped_keys,
                        "tenant": result.tenant,
                    },
                )
                return

            m = re.fullmatch(r"/v1/tenants/([^/]+)/activate", path)
            if m:
                from slack_mirror.service.tenant_onboarding import activate_tenant

                tenant_name = unquote(m.group(1))
                try:
                    result = activate_tenant(
                        config_path=config_path,
                        name=tenant_name,
                        dry_run=bool(body.get("dry_run", False)),
                        install_live_units=not bool(body.get("skip_live_units", False)),
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="tenants.activate")
                    return
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "changed": result.changed,
                        "dry_run": result.dry_run,
                        "config_path": result.config_path,
                        "backup_path": result.backup_path,
                        "live_units_installed": result.live_units_installed,
                        "live_unit_command": result.live_unit_command,
                        "tenant": result.tenant,
                    },
                )
                return

            m = re.fullmatch(r"/v1/tenants/([^/]+)/live", path)
            if m:
                from slack_mirror.service.tenant_onboarding import manage_tenant_live_units

                tenant_name = unquote(m.group(1))
                try:
                    result = manage_tenant_live_units(
                        config_path=config_path,
                        name=tenant_name,
                        action=str(body.get("action") or ""),
                        dry_run=bool(body.get("dry_run", False)),
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="tenants.live")
                    return
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "action": result.action,
                        "dry_run": result.dry_run,
                        "commands": result.commands,
                        "tenant": result.tenant,
                    },
                )
                return

            m = re.fullmatch(r"/v1/tenants/([^/]+)/backfill", path)
            if m:
                from slack_mirror.service.tenant_onboarding import run_tenant_backfill

                tenant_name = unquote(m.group(1))
                try:
                    result = run_tenant_backfill(
                        config_path=config_path,
                        name=tenant_name,
                        auth_mode=str(body.get("auth_mode") or "user"),
                        include_messages=bool(body.get("include_messages", True)),
                        include_files=bool(body.get("include_files", False)),
                        channel_limit=int(body.get("channel_limit") or 10),
                        dry_run=bool(body.get("dry_run", False)),
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="tenants.backfill")
                    return
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "action": result.action,
                        "dry_run": result.dry_run,
                        "commands": result.commands,
                        "tenant": result.tenant,
                    },
                )
                return

            m = re.fullmatch(r"/v1/tenants/([^/]+)/retire", path)
            if m:
                from slack_mirror.service.tenant_onboarding import retire_tenant

                tenant_name = unquote(m.group(1))
                if str(body.get("confirm") or "") != tenant_name:
                    _error_response(self, 400, "BAD_REQUEST", "confirm must exactly match tenant name")
                    return
                try:
                    result = retire_tenant(
                        config_path=config_path,
                        name=tenant_name,
                        delete_db=bool(body.get("delete_db", False)),
                        stop_live_units=bool(body.get("stop_live_units", True)),
                        dry_run=bool(body.get("dry_run", False)),
                    )
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="tenants.retire")
                    return
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "changed": result.changed,
                        "dry_run": result.dry_run,
                        "config_path": result.config_path,
                        "backup_path": result.backup_path,
                        "db_deleted": result.db_deleted,
                        "db_counts": result.db_counts,
                        "live_unit_commands": result.live_unit_commands,
                        "tenant": result.tenant,
                    },
                )
                return

            m = re.fullmatch(r"/v1/exports/([^/]+)/rename", path)
            if m:
                try:
                    payload = service.rename_export(
                        export_id=m.group(1),
                        new_export_id=str(body.get("export_id") or ""),
                        audience=str(body.get("audience") or "local"),
                    )
                except FileNotFoundError:
                    _error_response(self, 404, "NOT_FOUND", f"Export bundle not found: {m.group(1)}")
                    return
                except FileExistsError:
                    _error_response(self, 409, "CONFLICT", f"Export bundle already exists: {body.get('export_id')}")
                    return
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="exports.rename")
                    return
                _json_response(self, 200, {"ok": True, "export": payload})
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
            if self._is_protected_frontend_path(path):
                auth_session = self._enforce_frontend_auth(path)
                if auth_session is None:
                    return
            if _requires_same_origin_write(path):
                csrf_error = _validate_same_origin_post(self, export_base_urls=export_base_urls)
                if csrf_error:
                    _error_response(self, 403, "CSRF_FAILED", csrf_error)
                    return

            m = re.fullmatch(r"/v1/runtime/reports/([^/]+)", path)
            if m:
                try:
                    deleted = service.delete_runtime_report(name=m.group(1))
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="runtime.reports.delete")
                    return
                if not deleted:
                    _error_response(self, 404, "NOT_FOUND", f"Runtime report not found: {m.group(1)}")
                    return
                _json_response(self, 200, {"ok": True, "deleted": True, "name": m.group(1)})
                return

            m = re.fullmatch(r"/v1/exports/([^/]+)", path)
            if m:
                try:
                    deleted = service.delete_export(export_id=m.group(1))
                except Exception as exc:  # noqa: BLE001
                    _service_error_response(self, exc, path=path, operation="exports.delete")
                    return
                if not deleted:
                    _error_response(self, 404, "NOT_FOUND", f"Export bundle not found: {m.group(1)}")
                    return
                _json_response(self, 200, {"ok": True, "deleted": True, "export_id": m.group(1)})
                return

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
