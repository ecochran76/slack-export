from __future__ import annotations

import json
import mimetypes
import re
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from slack_mirror.core.config import load_config
from slack_mirror.exports import resolve_export_root, safe_export_path
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
    export_root = resolve_export_root(config)

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
