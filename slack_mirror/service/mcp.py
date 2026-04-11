from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from typing import Any, TextIO

from slack_mirror import __version__
from slack_mirror.service.app import get_app_service
from slack_mirror.service.errors import map_service_error


def _tool(name: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": schema,
    }


def _text_content(payload: Any) -> list[dict[str, str]]:
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, indent=2, sort_keys=True)
    return [{"type": "text", "text": text}]


class SlackMirrorMcpServer:
    def __init__(self, config_path: str | None = None):
        self.service = get_app_service(config_path)

    def tools(self) -> list[dict[str, Any]]:
        return [
            _tool("health", "Show service health summary", {"type": "object", "properties": {}, "additionalProperties": False}),
            _tool(
                "runtime.live_validation",
                "Validate managed runtime or full live-service health",
                {
                    "type": "object",
                    "properties": {
                        "require_live_units": {"type": "boolean", "default": True},
                    },
                    "additionalProperties": False,
                },
            ),
            _tool("workspaces.list", "List configured workspaces", {"type": "object", "properties": {}, "additionalProperties": False}),
            _tool(
                "search.corpus",
                "Search messages plus derived attachment and OCR text",
                {
                    "type": "object",
                    "properties": {
                        "workspace": {"type": "string"},
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                        "mode": {"type": "string", "enum": ["lexical", "semantic", "hybrid"], "default": "hybrid"},
                        "model": {"type": "string", "default": "local-hash-128"},
                        "lexical_weight": {"type": "number", "default": 0.6},
                        "semantic_weight": {"type": "number", "default": 0.4},
                        "semantic_scale": {"type": "number", "default": 10.0},
                        "no_fts": {"type": "boolean", "default": False},
                        "kind": {"type": "string", "enum": ["attachment_text", "ocr_text"]},
                        "source_kind": {"type": "string", "enum": ["file", "canvas"]},
                    },
                    "required": ["workspace", "query"],
                },
            ),
            _tool(
                "search.readiness",
                "Show workspace search readiness across messages, embeddings, attachment text, and OCR",
                {
                    "type": "object",
                    "properties": {"workspace": {"type": "string"}},
                    "required": ["workspace"],
                },
            ),
            _tool(
                "workspace.status",
                "Show workspace status and freshness",
                {
                    "type": "object",
                    "properties": {
                        "workspace": {"type": "string"},
                        "stale_hours": {"type": "number", "default": 24.0},
                        "max_zero_msg": {"type": "integer", "default": 0},
                        "max_stale": {"type": "integer", "default": 0},
                        "enforce_stale": {"type": "boolean", "default": False},
                    },
                    "required": ["workspace"],
                },
            ),
            _tool(
                "messages.send",
                "Send a message to a channel",
                {
                    "type": "object",
                    "properties": {
                        "workspace": {"type": "string"},
                        "channel_ref": {"type": "string"},
                        "text": {"type": "string"},
                        "options": {"type": "object", "default": {}},
                    },
                    "required": ["workspace", "channel_ref", "text"],
                },
            ),
            _tool(
                "threads.reply",
                "Send a reply in a thread",
                {
                    "type": "object",
                    "properties": {
                        "workspace": {"type": "string"},
                        "channel_ref": {"type": "string"},
                        "thread_ref": {"type": "string"},
                        "text": {"type": "string"},
                        "options": {"type": "object", "default": {}},
                    },
                    "required": ["workspace", "channel_ref", "thread_ref", "text"],
                },
            ),
            _tool(
                "listeners.list",
                "List listeners in a workspace",
                {"type": "object", "properties": {"workspace": {"type": "string"}}, "required": ["workspace"]},
            ),
            _tool(
                "listeners.status",
                "Inspect a listener",
                {
                    "type": "object",
                    "properties": {
                        "workspace": {"type": "string"},
                        "listener_id": {"type": "integer"},
                    },
                    "required": ["workspace", "listener_id"],
                },
            ),
            _tool(
                "listeners.register",
                "Register a listener",
                {
                    "type": "object",
                    "properties": {
                        "workspace": {"type": "string"},
                        "spec": {"type": "object"},
                    },
                    "required": ["workspace", "spec"],
                },
            ),
            _tool(
                "listeners.unregister",
                "Remove a listener",
                {
                    "type": "object",
                    "properties": {
                        "workspace": {"type": "string"},
                        "listener_id": {"type": "integer"},
                    },
                    "required": ["workspace", "listener_id"],
                },
            ),
            _tool(
                "deliveries.list",
                "List pending or processed listener deliveries",
                {
                    "type": "object",
                    "properties": {
                        "workspace": {"type": "string"},
                        "status": {"type": "string", "default": "pending"},
                        "listener_id": {"type": "integer"},
                        "limit": {"type": "integer", "default": 100},
                    },
                    "required": ["workspace"],
                },
            ),
            _tool(
                "deliveries.ack",
                "Acknowledge a listener delivery",
                {
                    "type": "object",
                    "properties": {
                        "workspace": {"type": "string"},
                        "delivery_id": {"type": "integer"},
                        "status": {"type": "string", "default": "delivered"},
                        "error": {"type": ["string", "null"]},
                    },
                    "required": ["workspace", "delivery_id"],
                },
            ),
        ]

    def _mcp_result(self, payload: Any) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if is_dataclass(value):
                return {k: convert(v) for k, v in asdict(value).items()}
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if isinstance(value, list):
                return [convert(v) for v in value]
            return value

        payload = convert(payload)
        return {"content": _text_content(payload)}

    def handle_call(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args = arguments or {}
        conn = self.service.connect()

        if name == "health":
            return self._mcp_result({"ok": True})
        if name == "runtime.live_validation":
            return self._mcp_result(
                self.service.validate_live_runtime(
                    require_live_units=bool(args.get("require_live_units", True)),
                )
            )
        if name == "workspaces.list":
            return self._mcp_result({"workspaces": self.service.list_workspaces(conn)})
        if name == "search.corpus":
            return self._mcp_result(
                {
                    "results": self.service.corpus_search(
                        conn,
                        workspace=str(args["workspace"]),
                        query=str(args["query"]),
                        limit=int(args.get("limit", 20)),
                        mode=str(args.get("mode", "hybrid")),
                        model_id=str(args.get("model", "local-hash-128")),
                        lexical_weight=float(args.get("lexical_weight", 0.6)),
                        semantic_weight=float(args.get("semantic_weight", 0.4)),
                        semantic_scale=float(args.get("semantic_scale", 10.0)),
                        use_fts=not bool(args.get("no_fts", False)),
                        derived_kind=str(args["kind"]) if args.get("kind") is not None else None,
                        derived_source_kind=str(args["source_kind"]) if args.get("source_kind") is not None else None,
                    )
                }
            )
        if name == "search.readiness":
            return self._mcp_result(
                self.service.search_readiness(
                    conn,
                    workspace=str(args["workspace"]),
                )
            )
        if name == "workspace.status":
            summary, rows = self.service.get_workspace_status(
                conn,
                workspace=str(args["workspace"]),
                stale_hours=float(args.get("stale_hours", 24.0)),
                max_zero_msg=int(args.get("max_zero_msg", 0)),
                max_stale=int(args.get("max_stale", 0)),
                enforce_stale=bool(args.get("enforce_stale", False)),
            )
            return self._mcp_result({"summary": summary, "rows": rows})
        if name == "messages.send":
            return self._mcp_result(
                self.service.send_message(
                    conn,
                    workspace=str(args["workspace"]),
                    channel_ref=str(args["channel_ref"]),
                    text=str(args["text"]),
                    options=dict(args.get("options") or {}),
                )
            )
        if name == "threads.reply":
            return self._mcp_result(
                self.service.send_thread_reply(
                    conn,
                    workspace=str(args["workspace"]),
                    channel_ref=str(args["channel_ref"]),
                    thread_ref=str(args["thread_ref"]),
                    text=str(args["text"]),
                    options=dict(args.get("options") or {}),
                )
            )
        if name == "listeners.list":
            return self._mcp_result({"listeners": self.service.list_listeners(conn, workspace=str(args["workspace"]))})
        if name == "listeners.status":
            return self._mcp_result(
                self.service.get_listener_status(
                    conn,
                    workspace=str(args["workspace"]),
                    listener_id=int(args["listener_id"]),
                )
            )
        if name == "listeners.register":
            return self._mcp_result(
                self.service.register_listener(
                    conn,
                    workspace=str(args["workspace"]),
                    spec=dict(args["spec"]),
                )
            )
        if name == "listeners.unregister":
            self.service.unregister_listener(
                conn,
                workspace=str(args["workspace"]),
                listener_id=int(args["listener_id"]),
            )
            return self._mcp_result({"ok": True})
        if name == "deliveries.list":
            return self._mcp_result(
                {
                    "deliveries": self.service.list_listener_deliveries(
                        conn,
                        workspace=str(args["workspace"]),
                        status=args.get("status", "pending"),
                        listener_id=int(args["listener_id"]) if args.get("listener_id") is not None else None,
                        limit=int(args.get("limit", 100)),
                    )
                }
            )
        if name == "deliveries.ack":
            self.service.ack_listener_delivery(
                conn,
                workspace=str(args["workspace"]),
                delivery_id=int(args["delivery_id"]),
                status=str(args.get("status", "delivered")),
                error=args.get("error"),
            )
            return self._mcp_result({"ok": True})
        raise ValueError(f"Unknown tool: {name}")

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "slack-mirror", "version": __version__},
                    "capabilities": {"tools": {}},
                },
            }

        if method == "initialized":
            return None

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": self.tools()},
            }

        if method == "tools/call":
            params = request.get("params") or {}
            try:
                result = self.handle_call(str(params.get("name") or ""), dict(params.get("arguments") or {}))
                return {"jsonrpc": "2.0", "id": request_id, "result": result}
            except Exception as exc:  # noqa: BLE001
                error = map_service_error(
                    exc,
                    tool=str(params.get("name") or ""),
                    arguments=dict(params.get("arguments") or {}),
                )
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": error.mcp_status, "message": error.message, "data": error.envelope()},
                }

        if request_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }
        return None


def _read_mcp_frame(stream: Any) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in {b"\r\n", b"\n"}:
            break
        key, _, value = line.decode("utf-8").partition(":")
        headers[key.strip().lower()] = value.strip()
    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        return None
    body = stream.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _write_mcp_frame(stream: Any, message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8"))
    stream.write(body)
    stream.flush()


def run_mcp_stdio(*, config_path: str | None = None, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
    server = SlackMirrorMcpServer(config_path)
    in_stream = (stdin or sys.stdin).buffer
    out_stream = (stdout or sys.stdout).buffer
    while True:
        request = _read_mcp_frame(in_stream)
        if request is None:
            return
        response = server.handle_request(request)
        if response is not None:
            _write_mcp_frame(out_stream, response)
