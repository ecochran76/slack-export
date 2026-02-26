from __future__ import annotations

import json
import secrets
import ssl
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests


@dataclass
class OAuthCallbackResult:
    code: str
    state: str | None
    error: str | None


def build_install_url(
    *,
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    user_scopes: list[str] | None = None,
    state: str | None = None,
) -> str:
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": ",".join([s for s in scopes if s]),
    }
    if user_scopes:
        params["user_scope"] = ",".join([s for s in user_scopes if s])
    if state:
        params["state"] = state
    return f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"


def exchange_oauth_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    res = requests.post(
        "https://slack.com/api/oauth.v2.access",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=timeout_seconds,
    )
    res.raise_for_status()
    payload = res.json()
    if not payload.get("ok"):
        raise RuntimeError(f"oauth.v2.access failed: {payload.get('error')}")
    return payload


def run_local_oauth_callback(
    *,
    bind: str,
    port: int,
    callback_path: str,
    cert_file: str,
    key_file: str,
    timeout_seconds: int,
    expected_state: str | None,
) -> OAuthCallbackResult:
    callback_path = callback_path if callback_path.startswith("/") else "/" + callback_path
    done = threading.Event()
    result: dict[str, str | None] = {"code": None, "state": None, "error": None}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != callback_path:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Not Found")
                return

            q = parse_qs(parsed.query)
            code = (q.get("code") or [None])[0]
            state = (q.get("state") or [None])[0]
            error = (q.get("error") or [None])[0]

            if expected_state and state != expected_state:
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"OAuth state mismatch. Close this tab and retry.")
                result.update({"error": "state_mismatch", "state": state, "code": None})
                done.set()
                return

            if error:
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"Slack OAuth error: {error}".encode("utf-8"))
                result.update({"error": error, "state": state, "code": None})
                done.set()
                return

            if not code:
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Missing code parameter")
                result.update({"error": "missing_code", "state": state, "code": None})
                done.set()
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Slack OAuth complete</h1><p>You can close this tab.</p></body></html>"
            )
            result.update({"code": code, "state": state, "error": None})
            done.set()

        def log_message(self, format: str, *args):
            return

    server = ThreadingHTTPServer((bind, port), _Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)

    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    thread.start()
    if not done.wait(timeout_seconds):
        server.shutdown()
        thread.join(timeout=2)
        raise TimeoutError("Timed out waiting for Slack OAuth callback")

    server.shutdown()
    thread.join(timeout=2)

    return OAuthCallbackResult(
        code=str(result["code"] or ""),
        state=result["state"],
        error=result["error"],
    )


def generate_state() -> str:
    return secrets.token_urlsafe(24)


def format_tokens_summary(payload: dict[str, Any]) -> str:
    summary = {
        "ok": payload.get("ok"),
        "team": payload.get("team", {}),
        "app_id": payload.get("app_id"),
        "scope": payload.get("scope"),
        "authed_user": {
            "id": payload.get("authed_user", {}).get("id"),
            "scope": payload.get("authed_user", {}).get("scope"),
        },
        "token_type": payload.get("token_type"),
        "access_token": payload.get("access_token"),
        "bot_user_id": payload.get("bot_user_id"),
        "authed_user_access_token": payload.get("authed_user", {}).get("access_token"),
    }
    return json.dumps(summary, indent=2)


def maybe_open_browser(url: str) -> None:
    webbrowser.open(url)
