from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import traceback
import time
from dataclasses import asdict, is_dataclass
from typing import Any, TextIO

from slack_mirror import __version__
from slack_mirror.service.app import get_app_service
from slack_mirror.service.errors import map_service_error

MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_SUPPORTED_PROTOCOL_VERSIONS = {
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
}
McpTransport = str


def _mcp_trace_enabled() -> bool:
    return os.environ.get("SLACK_MIRROR_MCP_TRACE", "").strip().lower() in {"1", "true", "yes", "on"}


def _mcp_trace(event: str, **fields: Any) -> None:
    if not _mcp_trace_enabled():
        return
    payload = {
        "ts": round(time.time(), 6),
        "event": event,
        "pid": os.getpid(),
    }
    for key, value in fields.items():
        if value is not None:
            payload[key] = value
    line = json.dumps(payload, sort_keys=True)
    trace_path = os.environ.get("SLACK_MIRROR_MCP_TRACE_FILE", "").strip()
    if trace_path:
        with open(trace_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return
    print(line, file=sys.stderr, flush=True)


def _describe_stream(stream: Any, *, label: str) -> dict[str, Any]:
    details: dict[str, Any] = {"label": label}
    try:
        fileno = stream.fileno()
    except Exception as exc:  # pragma: no cover - debug-only path
        details["fileno_error"] = repr(exc)
        return details

    details["fileno"] = fileno
    try:
        details["isatty"] = bool(stream.isatty())
    except Exception as exc:  # pragma: no cover - debug-only path
        details["isatty_error"] = repr(exc)
    fd_path = Path(f"/proc/self/fd/{fileno}")
    try:
        details["fd_target"] = os.readlink(fd_path)
    except OSError as exc:  # pragma: no cover - platform/debug-only path
        details["fd_target_error"] = repr(exc)
    return details


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
        _mcp_trace("server.init.begin", config_path=config_path)
        self.service = get_app_service(config_path)
        _mcp_trace("server.init.ready", config_path=config_path)

    @staticmethod
    def _negotiate_protocol_version(params: dict[str, Any]) -> str:
        requested = params.get("protocolVersion")
        if isinstance(requested, str) and requested in MCP_SUPPORTED_PROTOCOL_VERSIONS:
            return requested
        return MCP_PROTOCOL_VERSION

    def tools(self) -> list[dict[str, Any]]:
        return [
            _tool("health", "Show service health summary", {"type": "object", "properties": {}, "additionalProperties": False}),
            _tool("runtime.status", "Show managed runtime status and latest reconcile summary", {"type": "object", "properties": {}, "additionalProperties": False}),
            _tool(
                "runtime.report.latest",
                "Show the latest managed runtime report manifest",
                {"type": "object", "properties": {}, "additionalProperties": False},
            ),
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
                        "all_workspaces": {"type": "boolean", "default": False},
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                        "mode": {"type": "string", "enum": ["lexical", "semantic", "hybrid"], "default": "hybrid"},
                        "model": {"type": "string", "default": "local-hash-128"},
                        "lexical_weight": {"type": "number", "default": 0.6},
                        "semantic_weight": {"type": "number", "default": 0.4},
                        "semantic_scale": {"type": "number", "default": 10.0},
                        "fusion": {"type": "string", "enum": ["weighted", "rrf"], "default": "weighted"},
                        "no_fts": {"type": "boolean", "default": False},
                        "rerank": {"type": "boolean", "default": False},
                        "rerank_top_n": {"type": "integer", "default": 50},
                        "kind": {"type": "string", "enum": ["attachment_text", "ocr_text"]},
                        "source_kind": {"type": "string", "enum": ["file", "canvas"]},
                    },
                    "required": ["query"],
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
                "search.profiles",
                "List semantic retrieval profiles",
                {"type": "object", "properties": {}, "additionalProperties": False},
            ),
            _tool(
                "search.semantic_readiness",
                "Show retrieval-profile semantic readiness for one workspace or all enabled workspaces",
                {
                    "type": "object",
                    "properties": {
                        "workspace": {"type": "string"},
                        "profiles": {"type": "array", "items": {"type": "string"}},
                        "include_commands": {"type": "boolean", "default": False},
                        "command_limit": {"type": "integer", "default": 500},
                    },
                    "additionalProperties": False,
                },
            ),
            _tool(
                "search.health",
                "Run search health checks over readiness and optional benchmark dataset",
                {
                    "type": "object",
                    "properties": {
                        "workspace": {"type": "string"},
                        "dataset_path": {"type": "string"},
                        "mode": {"type": "string", "enum": ["lexical", "semantic", "hybrid"], "default": "hybrid"},
                        "limit": {"type": "integer", "default": 10},
                        "model": {"type": "string", "default": "local-hash-128"},
                        "min_hit_at_3": {"type": "number", "default": 0.5},
                        "min_hit_at_10": {"type": "number", "default": 0.8},
                        "min_ndcg_at_k": {"type": "number", "default": 0.6},
                        "max_latency_p95_ms": {"type": "number", "default": 800.0},
                    },
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
        if name == "runtime.status":
            return self._mcp_result(self.service.runtime_status())
        if name == "runtime.report.latest":
            payload = self.service.latest_runtime_report()
            if payload is None:
                return self._mcp_result({"ok": False, "error": {"code": "NOT_FOUND", "message": "No runtime reports available"}})
            return self._mcp_result({"ok": True, "report": payload})
        if name == "runtime.live_validation":
            return self._mcp_result(
                self.service.validate_live_runtime(
                    require_live_units=bool(args.get("require_live_units", True)),
                )
            )
        if name == "workspaces.list":
            return self._mcp_result({"workspaces": self.service.list_workspaces(conn)})
        if name == "search.corpus":
            workspace = str(args["workspace"]) if args.get("workspace") is not None else None
            all_workspaces = bool(args.get("all_workspaces", False))
            return self._mcp_result(
                {
                    "results": self.service.corpus_search(
                        conn,
                        workspace=workspace,
                        all_workspaces=all_workspaces,
                        query=str(args["query"]),
                        limit=int(args.get("limit", 20)),
                        mode=str(args.get("mode", "hybrid")),
                        model_id=str(args.get("model", "local-hash-128")),
                        lexical_weight=float(args.get("lexical_weight", 0.6)),
                        semantic_weight=float(args.get("semantic_weight", 0.4)),
                        semantic_scale=float(args.get("semantic_scale", 10.0)),
                        fusion_method=str(args.get("fusion", "weighted")),
                        use_fts=not bool(args.get("no_fts", False)),
                        derived_kind=str(args["kind"]) if args.get("kind") is not None else None,
                        derived_source_kind=str(args["source_kind"]) if args.get("source_kind") is not None else None,
                        rerank=bool(args.get("rerank", False)),
                        rerank_top_n=int(args.get("rerank_top_n", 50)),
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
        if name == "search.profiles":
            return self._mcp_result({"profiles": self.service.retrieval_profiles()})
        if name == "search.semantic_readiness":
            raw_profiles = args.get("profiles")
            profile_names = [str(item) for item in raw_profiles] if isinstance(raw_profiles, list) else None
            return self._mcp_result(
                self.service.semantic_readiness(
                    conn,
                    workspace=str(args["workspace"]) if args.get("workspace") is not None else None,
                    profile_names=profile_names,
                    include_commands=bool(args.get("include_commands", False)),
                    command_limit=int(args.get("command_limit", 500)),
                )
            )
        if name == "search.health":
            return self._mcp_result(
                self.service.search_health(
                    conn,
                    workspace=str(args["workspace"]),
                    dataset_path=str(args["dataset_path"]) if args.get("dataset_path") is not None else None,
                    mode=str(args.get("mode", "hybrid")),
                    limit=int(args.get("limit", 10)),
                    model_id=str(args.get("model", "local-hash-128")),
                    min_hit_at_3=float(args.get("min_hit_at_3", 0.5)),
                    min_hit_at_10=float(args.get("min_hit_at_10", 0.8)),
                    min_ndcg_at_k=float(args.get("min_ndcg_at_k", 0.6)),
                    max_latency_p95_ms=float(args.get("max_latency_p95_ms", 800.0)),
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
        _mcp_trace("request.received", method=method, request_id=request_id)

        if method == "initialize":
            params = request.get("params") or {}
            negotiated_protocol = self._negotiate_protocol_version(dict(params))
            _mcp_trace(
                "request.initialize",
                request_id=request_id,
                requested_protocol=params.get("protocolVersion"),
                negotiated_protocol=negotiated_protocol,
                client_info=params.get("clientInfo"),
            )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": negotiated_protocol,
                    "serverInfo": {"name": "slack-mirror", "version": __version__},
                    "capabilities": {"tools": {}},
                },
            }

        if method == "initialized":
            _mcp_trace("request.initialized", request_id=request_id)
            return None

        if method == "tools/list":
            _mcp_trace("request.tools_list", request_id=request_id)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": self.tools()},
            }

        if method == "tools/call":
            params = request.get("params") or {}
            try:
                _mcp_trace("request.tools_call.begin", request_id=request_id, tool=params.get("name"))
                result = self.handle_call(str(params.get("name") or ""), dict(params.get("arguments") or {}))
                _mcp_trace("request.tools_call.ok", request_id=request_id, tool=params.get("name"))
                return {"jsonrpc": "2.0", "id": request_id, "result": result}
            except Exception as exc:  # noqa: BLE001
                error = map_service_error(
                    exc,
                    tool=str(params.get("name") or ""),
                    arguments=dict(params.get("arguments") or {}),
                )
                _mcp_trace(
                    "request.tools_call.error",
                    request_id=request_id,
                    tool=params.get("name"),
                    error_code=error.mcp_status,
                    error_message=error.message,
                )
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": error.mcp_status, "message": error.message, "data": error.envelope()},
                }

        if request_id is not None:
            _mcp_trace("request.unknown_method", request_id=request_id, method=method)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }
        return None


def _read_mcp_frame(stream: Any) -> tuple[dict[str, Any], McpTransport] | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            _mcp_trace("frame.read.eof")
            return None
        if line in {b"\r\n", b"\n"}:
            break
        decoded_line = line.decode("utf-8", errors="replace")
        stripped_line = decoded_line.strip()
        if not headers and stripped_line.startswith("{"):
            payload = json.loads(decoded_line)
            _mcp_trace(
                "frame.read.jsonl",
                content_length=len(line),
                method=payload.get("method"),
                request_id=payload.get("id"),
            )
            return payload, "jsonl"
        if ":" not in decoded_line:
            _mcp_trace(
                "frame.read.invalid_header_line",
                raw_line=decoded_line[:400],
                raw_line_hex=line[:64].hex(),
            )
            raise ValueError(f"Invalid MCP header line: {decoded_line!r}")
        key, _, value = decoded_line.partition(":")
        headers[key.strip().lower()] = value.strip()
    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        _mcp_trace("frame.read.invalid_length", headers=headers)
        return None
    body = stream.read(content_length)
    if not body:
        _mcp_trace("frame.read.empty_body", content_length=content_length)
        return None
    payload = json.loads(body.decode("utf-8"))
    _mcp_trace(
        "frame.read.ok",
        content_length=content_length,
        method=payload.get("method"),
        request_id=payload.get("id"),
    )
    return payload, "content-length"


def _write_mcp_frame(stream: Any, message: dict[str, Any], *, transport: McpTransport) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    _mcp_trace(
        "frame.write",
        content_length=len(body),
        method=message.get("method"),
        request_id=message.get("id"),
        has_error="error" in message,
        transport=transport,
    )
    if transport == "jsonl":
        stream.write(body + b"\n")
    else:
        stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8"))
        stream.write(body)
    stream.flush()


def run_mcp_stdio(*, config_path: str | None = None, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
    server = SlackMirrorMcpServer(config_path)
    in_stream = (stdin or sys.stdin).buffer
    out_stream = (stdout or sys.stdout).buffer
    _mcp_trace(
        "server.stdio.ready",
        argv=sys.argv,
        cwd=os.getcwd(),
        ppid=os.getppid(),
        stdin=_describe_stream(in_stream, label="stdin"),
        stdout=_describe_stream(out_stream, label="stdout"),
    )
    while True:
        _mcp_trace("frame.read.wait")
        try:
            frame = _read_mcp_frame(in_stream)
        except Exception as exc:  # noqa: BLE001
            _mcp_trace(
                "frame.read.exception",
                error_type=type(exc).__name__,
                error_message=str(exc),
                traceback="".join(traceback.format_exception(exc)),
            )
            raise
        if frame is None:
            return
        request, transport = frame
        response = server.handle_request(request)
        if response is not None:
            _write_mcp_frame(out_stream, response, transport=transport)
