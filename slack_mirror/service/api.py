from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

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

    class Handler(BaseHTTPRequestHandler):
        def _query(self) -> dict[str, list[str]]:
            return parse_qs(urlparse(self.path).query)

        def _path(self) -> str:
            return urlparse(self.path).path.rstrip("/") or "/"

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

            if path == "/v1/health":
                _json_response(self, 200, {"ok": True})
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

            _error_response(self, 404, "NOT_FOUND", f"Unknown path: {path}")

        def do_POST(self):  # noqa: N802
            path = self._path()
            query = self._query()
            try:
                body = _parse_json_body(self)
            except json.JSONDecodeError as exc:
                _error_response(self, 400, "BAD_REQUEST", f"Invalid JSON: {exc}")
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
