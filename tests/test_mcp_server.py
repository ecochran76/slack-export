import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from slack_mirror import __version__
from slack_mirror.service.app import LiveValidationResult
from slack_mirror.service.mcp import SlackMirrorMcpServer, run_mcp_stdio


def _frame(message: dict) -> bytes:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body


def _parse_frames(payload: bytes) -> list[dict]:
    frames: list[dict] = []
    buf = memoryview(payload)
    offset = 0
    while offset < len(buf):
        header_end = payload.find(b"\r\n\r\n", offset)
        if header_end == -1:
            break
        header_block = payload[offset:header_end].decode("utf-8")
        headers = {}
        for line in header_block.split("\r\n"):
            if not line:
                continue
            key, _, value = line.partition(":")
            headers[key.strip().lower()] = value.strip()
        content_length = int(headers["content-length"])
        body_start = header_end + 4
        body_end = body_start + content_length
        frames.append(json.loads(payload[body_start:body_end].decode("utf-8")))
        offset = body_end
    return frames


def _parse_jsonl(payload: bytes) -> list[dict]:
    return [json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()]


class _BufferStream:
    def __init__(self, initial: bytes = b""):
        self.buffer = io.BytesIO(initial)


def _result_payload(response: dict) -> dict:
    return json.loads(response["result"]["content"][0]["text"])


class McpServerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.config_path = self.root / "config.yaml"
        self.db_path = self.root / "data" / "mirror.db"
        self.config_path.write_text(
            "\n".join(
                [
                    "version: 1",
                    "storage:",
                    f"  db_path: {self.db_path}",
                    "workspaces:",
                    "  - name: default",
                    "    team_id: T123",
                    "    token: xoxb-test-token",
                    "    user_token: xoxp-test-token",
                    "  - name: soylei",
                    "    team_id: T456",
                    "    token: xoxb-soylei-token",
                    "    user_token: xoxp-soylei-token",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.server = SlackMirrorMcpServer(str(self.config_path))

    def test_initialize_and_tools_list(self):
        init = self.server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "slack-mirror")
        self.assertEqual(init["result"]["serverInfo"]["version"], __version__)
        self.assertIn("tools", init["result"]["capabilities"])

        tools = self.server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = [tool["name"] for tool in tools["result"]["tools"]]
        self.assertIn("health", names)
        self.assertIn("runtime.status", names)
        self.assertIn("runtime.report.latest", names)
        self.assertIn("runtime.live_validation", names)
        self.assertIn("search.corpus", names)
        self.assertIn("search.health", names)
        self.assertIn("search.readiness", names)
        self.assertIn("search.profiles", names)
        self.assertIn("search.semantic_readiness", names)
        self.assertIn("messages.send", names)
        self.assertIn("listeners.register", names)

    def test_initialize_negotiates_supported_protocol_version(self):
        init = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26"},
            }
        )
        self.assertEqual(init["result"]["protocolVersion"], "2025-03-26")

    def test_initialize_trace_file_records_handshake(self):
        trace_path = self.root / "mcp-trace.jsonl"
        input_stream = _BufferStream(
            _frame(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "clientInfo": {"name": "codex-probe", "version": "0.118.0"},
                    },
                }
            )
        )
        output_stream = _BufferStream()
        with patch.dict(
            os.environ,
            {
                "SLACK_MIRROR_MCP_TRACE": "1",
                "SLACK_MIRROR_MCP_TRACE_FILE": str(trace_path),
            },
            clear=False,
        ):
            run_mcp_stdio(config_path=str(self.config_path), stdin=input_stream, stdout=output_stream)
        lines = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        events = [entry["event"] for entry in lines]
        self.assertIn("server.init.begin", events)
        self.assertIn("server.init.ready", events)
        self.assertIn("server.stdio.ready", events)
        self.assertIn("request.initialize", events)
        stdio_ready = next(entry for entry in lines if entry["event"] == "server.stdio.ready")
        self.assertEqual(stdio_ready["stdin"]["label"], "stdin")
        self.assertEqual(stdio_ready["stdout"]["label"], "stdout")
        initialize = next(entry for entry in lines if entry["event"] == "request.initialize")
        self.assertEqual(initialize["requested_protocol"], "2025-03-26")
        self.assertEqual(initialize["negotiated_protocol"], "2025-03-26")

    def test_tools_call_round_trip_via_stdio(self):
        input_stream = _BufferStream(
            _frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            + _frame({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "health", "arguments": {}}})
        )
        output_stream = _BufferStream()

        run_mcp_stdio(config_path=str(self.config_path), stdin=input_stream, stdout=output_stream)
        responses = _parse_frames(output_stream.buffer.getvalue())
        self.assertEqual(responses[0]["id"], 1)
        self.assertEqual(responses[1]["id"], 2)
        health_text = responses[1]["result"]["content"][0]["text"]
        self.assertIn('"ok": true', health_text)

    def test_tools_call_round_trip_via_jsonl_stdio(self):
        input_stream = _BufferStream(
            (
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
                + "\n"
                + json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "health", "arguments": {}},
                    }
                )
                + "\n"
            ).encode("utf-8")
        )
        output_stream = _BufferStream()

        run_mcp_stdio(config_path=str(self.config_path), stdin=input_stream, stdout=output_stream)
        responses = _parse_jsonl(output_stream.buffer.getvalue())
        self.assertEqual(responses[0]["id"], 1)
        self.assertEqual(responses[1]["id"], 2)
        health_text = responses[1]["result"]["content"][0]["text"]
        self.assertIn('"ok": true', health_text)

    def test_invalid_header_line_traces_and_raises(self):
        trace_path = self.root / "mcp-invalid-trace.jsonl"
        input_stream = _BufferStream(b"not-a-header-line\n")
        output_stream = _BufferStream()
        with (
            patch.dict(
                os.environ,
                {
                    "SLACK_MIRROR_MCP_TRACE": "1",
                    "SLACK_MIRROR_MCP_TRACE_FILE": str(trace_path),
                },
                clear=False,
            ),
            self.assertRaises(ValueError),
        ):
            run_mcp_stdio(config_path=str(self.config_path), stdin=input_stream, stdout=output_stream)
        lines = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        events = [entry["event"] for entry in lines]
        self.assertIn("frame.read.invalid_header_line", events)
        self.assertIn("frame.read.exception", events)

    def test_message_send_and_listener_tools(self):
        with patch("slack_mirror.service.app.SlackApiClient") as mock_client_cls:
            client = mock_client_cls.return_value
            client.send_message.return_value = {"ok": True, "channel": "C123", "ts": "2000.0001"}
            send = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "messages.send",
                        "arguments": {
                            "workspace": "default",
                            "channel_ref": "C123",
                            "text": "hello",
                            "options": {"idempotency_key": "msg-1"},
                        },
                    },
                }
            )
        send_text = send["result"]["content"][0]["text"]
        self.assertIn('"status": "sent"', send_text)
        self.assertIn('"idempotent_replay": false', send_text)
        self.assertIn('"retryable": false', send_text)
        self.assertEqual(client.send_message.call_count, 1)

        replay = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {
                    "name": "messages.send",
                    "arguments": {
                        "workspace": "default",
                        "channel_ref": "C123",
                        "text": "hello",
                        "options": {"idempotency_key": "msg-1"},
                    },
                },
            }
        )
        self.assertIn('"idempotent_replay": true', replay["result"]["content"][0]["text"])

        register = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "listeners.register",
                    "arguments": {
                        "workspace": "default",
                        "spec": {"name": "hook", "event_types": ["message"], "channel_ids": ["C123"]},
                    },
                },
            }
        )
        self.assertIn('"name": "hook"', register["result"]["content"][0]["text"])

        conn = self.server.service.connect()
        self.addCleanup(conn.close)
        self.server.service.ingest_event(
            conn,
            workspace="default",
            event_id="evt-1",
            event_ts="2000.0002",
            event_type="message",
            payload={"event": {"type": "message", "channel": "C123", "ts": "2000.0002", "text": "hi"}},
        )

        deliveries = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "deliveries.list", "arguments": {"workspace": "default", "status": "pending"}},
            }
        )
        self.assertIn('"status": "pending"', deliveries["result"]["content"][0]["text"])

    def test_outbound_listener_delivery_lifecycle_tools(self):
        register = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 40,
                "method": "tools/call",
                "params": {
                    "name": "listeners.register",
                    "arguments": {
                        "workspace": "default",
                        "spec": {
                            "name": "outbound-hook",
                            "event_types": ["outbound.message.sent", "outbound.thread_reply.sent"],
                            "delivery_mode": "queue",
                        },
                    },
                },
            }
        )
        listener = _result_payload(register)
        listener_id = int(listener["id"])

        with patch("slack_mirror.service.app.SlackApiClient") as mock_client_cls:
            client = mock_client_cls.return_value
            client.send_message.return_value = {"ok": True, "channel": "C123", "ts": "2000.0001"}
            client.send_thread_reply.return_value = {
                "ok": True,
                "channel": "C123",
                "ts": "2000.0002",
                "thread_ts": "2000.0001",
            }

            send = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 41,
                    "method": "tools/call",
                    "params": {
                        "name": "messages.send",
                        "arguments": {
                            "workspace": "default",
                            "channel_ref": "C123",
                            "text": "hello from mcp",
                            "options": {"idempotency_key": "outbound-msg-1"},
                        },
                    },
                }
            )
            reply = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 42,
                    "method": "tools/call",
                    "params": {
                        "name": "threads.reply",
                        "arguments": {
                            "workspace": "default",
                            "channel_ref": "C123",
                            "thread_ref": "2000.0001",
                            "text": "reply from mcp",
                            "options": {"idempotency_key": "outbound-reply-1"},
                        },
                    },
                }
            )

        self.assertEqual(client.send_message.call_count, 1)
        client.send_thread_reply.assert_called_once_with(channel="C123", thread_ts="2000.0001", text="reply from mcp", idempotency_key="outbound-reply-1")
        self.assertEqual(_result_payload(send)["status"], "sent")
        self.assertEqual(_result_payload(reply)["status"], "sent")

        pending = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 43,
                "method": "tools/call",
                "params": {
                    "name": "deliveries.list",
                    "arguments": {"workspace": "default", "status": "pending", "listener_id": listener_id},
                },
            }
        )
        pending_payload = _result_payload(pending)
        deliveries = pending_payload["deliveries"]
        self.assertEqual(len(deliveries), 2)
        self.assertEqual(
            [item["event_type"] for item in deliveries],
            ["outbound.message.sent", "outbound.thread_reply.sent"],
        )

        for idx, delivery in enumerate(deliveries, start=44):
            ack = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": idx,
                    "method": "tools/call",
                    "params": {
                        "name": "deliveries.ack",
                        "arguments": {"workspace": "default", "delivery_id": int(delivery["id"])},
                    },
                }
            )
            self.assertTrue(_result_payload(ack)["ok"])

        delivered = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 46,
                "method": "tools/call",
                "params": {
                    "name": "deliveries.list",
                    "arguments": {"workspace": "default", "status": "delivered", "listener_id": listener_id},
                },
            }
        )
        delivered_payload = _result_payload(delivered)
        self.assertEqual(len(delivered_payload["deliveries"]), 2)
        self.assertEqual(
            {item["attempts"] for item in delivered_payload["deliveries"]},
            {1},
        )

        status = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 47,
                "method": "tools/call",
                "params": {
                    "name": "listeners.status",
                    "arguments": {"workspace": "default", "listener_id": listener_id},
                },
            }
        )
        self.assertEqual(_result_payload(status)["pending_deliveries"], 0)

        unregister = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 48,
                "method": "tools/call",
                "params": {
                    "name": "listeners.unregister",
                    "arguments": {"workspace": "default", "listener_id": listener_id},
                },
            }
        )
        self.assertTrue(_result_payload(unregister)["ok"])

        listeners = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 49,
                "method": "tools/call",
                "params": {
                    "name": "listeners.list",
                    "arguments": {"workspace": "default"},
                },
            }
        )
        self.assertEqual(_result_payload(listeners)["listeners"], [])

    def test_runtime_live_validation_tool(self):
        with patch.object(
            self.server.service,
            "validate_live_runtime",
            return_value=LiveValidationResult(
                ok=True,
                status="pass",
                require_live_units=False,
                summary="Summary: PASS",
                lines=["OK managed config present", "Summary: PASS"],
                exit_code=0,
                failure_count=0,
                warning_count=0,
                failure_codes=[],
                warning_codes=[],
                workspaces=[
                    {
                        "name": "default",
                        "event_errors": 0,
                        "embedding_errors": 0,
                        "event_pending": 0,
                        "embedding_pending": 0,
                        "failure_codes": [],
                        "warning_codes": [],
                    }
                ],
            ),
        ) as mock_validate:
            result = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "runtime.live_validation",
                        "arguments": {"require_live_units": False},
                    },
                }
            )
        text = result["result"]["content"][0]["text"]
        self.assertIn('"ok": true', text)
        self.assertIn('"status": "pass"', text)
        self.assertIn('"summary": "Summary: PASS"', text)
        self.assertIn('"workspaces"', text)
        mock_validate.assert_called_once_with(require_live_units=False)

    def test_runtime_status_tool(self):
        with patch.object(
            self.server.service,
            "runtime_status",
            return_value={
                "ok": True,
                "wrappers_present": True,
                "api_service_present": True,
                "config_present": True,
                "db_present": True,
                "cache_present": True,
                "rollback_snapshot_present": True,
                "services": {"slack-mirror-api.service": "active"},
                "reconcile_workspaces": [
                    {
                        "name": "default",
                        "state_present": True,
                        "auth_mode": "user",
                        "downloaded": 2,
                        "warnings": 0,
                        "failed": 0,
                    }
                ],
            },
        ) as mock_status:
            result = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 66,
                    "method": "tools/call",
                    "params": {
                        "name": "runtime.status",
                        "arguments": {},
                    },
                }
            )
        text = result["result"]["content"][0]["text"]
        self.assertIn('"wrappers_present": true', text)
        self.assertIn('"reconcile_workspaces"', text)
        self.assertIn('"name": "default"', text)
        mock_status.assert_called_once_with()

    def test_runtime_report_latest_tool(self):
        with patch.object(
            self.server.service,
            "latest_runtime_report",
            return_value={
                "name": "scheduled-runtime-report",
                "status": "pass_with_warnings",
                "summary": "Summary: PASS with warnings (1)",
            },
        ) as mock_latest:
            result = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 67,
                    "method": "tools/call",
                    "params": {
                        "name": "runtime.report.latest",
                        "arguments": {},
                    },
                }
            )
        text = result["result"]["content"][0]["text"]
        self.assertIn('"ok": true', text)
        self.assertIn('"name": "scheduled-runtime-report"', text)
        self.assertIn('"status": "pass_with_warnings"', text)
        mock_latest.assert_called_once_with()

    def test_runtime_report_latest_tool_handles_missing_reports(self):
        with patch.object(
            self.server.service,
            "latest_runtime_report",
            return_value=None,
        ) as mock_latest:
            result = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 68,
                    "method": "tools/call",
                    "params": {
                        "name": "runtime.report.latest",
                        "arguments": {},
                    },
                }
            )
        text = result["result"]["content"][0]["text"]
        self.assertIn('"ok": false', text)
        self.assertIn('"code": "NOT_FOUND"', text)
        mock_latest.assert_called_once_with()

    def test_search_tools(self):
        with patch.object(
            self.server.service,
            "corpus_search",
            return_value=[
                {
                    "result_kind": "message",
                    "source_label": "general",
                    "text": "incident review follow-up",
                    "_source": "hybrid",
                    "_hybrid_score": 5.1,
                    "action_target": {"version": 1, "kind": "message", "id": "message|default|C1|10.0"},
                }
            ],
        ) as mock_corpus, patch.object(
            self.server.service,
            "search_readiness",
            return_value={
                "workspace": "default",
                "status": "ready",
                "messages": {"count": 10, "embeddings": {"count": 10, "pending": 0, "errors": 0}},
                "derived_text": {
                    "attachment_text": {"count": 4, "pending": 0, "errors": 0},
                    "ocr_text": {"count": 2, "pending": 0, "errors": 0},
                },
            },
        ) as mock_readiness, patch.object(
            self.server.service,
            "retrieval_profiles",
            return_value=[{"name": "baseline", "model": "local-hash-128"}],
        ) as mock_profiles, patch.object(
            self.server.service,
            "build_search_context_pack",
            return_value={
                "schema_version": 1,
                "kind": "search_context_pack",
                "item_count": 1,
                "resolved_count": 1,
                "unresolved_count": 0,
                "items": [{"kind": "message", "resolved": True}],
                "unresolved": [],
            },
        ) as mock_context_pack, patch.object(
            self.server.service,
            "create_selected_result_export",
            return_value={
                "export_id": "selected-default-smoke",
                "kind": "selected-results",
                "item_count": 1,
                "resolved_count": 1,
            },
        ) as mock_context_export, patch.object(
            self.server.service,
            "semantic_readiness",
            return_value={
                "scope": "workspace",
                "workspace": "default",
                "workspaces": [{"workspace": "default", "status": "ready", "profiles": [{"name": "baseline", "state": "ready"}]}],
            },
        ) as mock_semantic_readiness:
            corpus = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 61,
                    "method": "tools/call",
                    "params": {
                        "name": "search.corpus",
                        "arguments": {
                            "workspace": "default",
                            "query": "incident review",
                            "retrieval_profile": "baseline",
                            "mode": "hybrid",
                            "fusion": "rrf",
                            "rerank": True,
                            "rerank_top_n": 25,
                        },
                    },
                }
            )
            readiness = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 62,
                    "method": "tools/call",
                    "params": {
                        "name": "search.readiness",
                        "arguments": {"workspace": "default"},
                    },
                }
            )
            corpus_all = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 64,
                    "method": "tools/call",
                    "params": {
                        "name": "search.corpus",
                        "arguments": {"all_workspaces": True, "query": "incident review", "mode": "hybrid"},
                    },
                }
            )
            profiles = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 65,
                    "method": "tools/call",
                    "params": {"name": "search.profiles", "arguments": {}},
                }
            )
            semantic_readiness = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 66,
                    "method": "tools/call",
                    "params": {
                        "name": "search.semantic_readiness",
                        "arguments": {"workspace": "default", "profiles": ["baseline"], "include_commands": True},
                    },
                }
            )
            context_pack = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 67,
                    "method": "tools/call",
                    "params": {
                        "name": "search.context_pack",
                        "arguments": {
                            "targets": [{"kind": "message", "workspace": "default", "channel_id": "C1", "ts": "10.0"}],
                            "before": 1,
                            "after": 1,
                        },
                    },
                }
            )
            context_export = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 68,
                    "method": "tools/call",
                    "params": {
                        "name": "search.context_export",
                        "arguments": {
                            "targets": [{"kind": "message", "workspace": "default", "channel_id": "C1", "ts": "10.0"}],
                            "before": 1,
                            "after": 1,
                            "include_text": False,
                            "export_id": "selected-default-smoke",
                            "title": "Smoke Selection",
                        },
                    },
                }
            )

        self.assertIn('"result_kind": "message"', corpus["result"]["content"][0]["text"])
        self.assertIn('"action_target"', corpus["result"]["content"][0]["text"])
        self.assertIn('"result_kind": "message"', corpus_all["result"]["content"][0]["text"])
        self.assertIn('"status": "ready"', readiness["result"]["content"][0]["text"])
        self.assertIn('"name": "baseline"', profiles["result"]["content"][0]["text"])
        self.assertIn('"status": "ready"', semantic_readiness["result"]["content"][0]["text"])
        self.assertIn('"kind": "search_context_pack"', context_pack["result"]["content"][0]["text"])
        self.assertIn('"kind": "selected-results"', context_export["result"]["content"][0]["text"])
        self.assertEqual(mock_corpus.call_count, 2)
        first_call = mock_corpus.call_args_list[0].kwargs
        self.assertTrue(first_call["rerank"])
        self.assertEqual(first_call["rerank_top_n"], 25)
        self.assertEqual(first_call["fusion_method"], "rrf")
        self.assertEqual(first_call["retrieval_profile_name"], "baseline")
        mock_readiness.assert_called_once_with(unittest.mock.ANY, workspace="default")
        mock_profiles.assert_called_once()
        mock_context_pack.assert_called_once()
        mock_context_export.assert_called_once()
        mock_semantic_readiness.assert_called_once()

    def test_search_corpus_schema_exposes_retrieval_profile(self):
        tools = self.server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        corpus_tool = next(tool for tool in tools["result"]["tools"] if tool["name"] == "search.corpus")
        context_export_tool = next(tool for tool in tools["result"]["tools"] if tool["name"] == "search.context_export")
        self.assertIn("retrieval_profile", corpus_tool["inputSchema"]["properties"])
        self.assertIn("targets", context_export_tool["inputSchema"]["required"])
        self.assertIn("audience", context_export_tool["inputSchema"]["properties"])

    def test_search_corpus_invalid_retrieval_profile_returns_structured_error(self):
        result = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 74,
                "method": "tools/call",
                "params": {
                    "name": "search.corpus",
                    "arguments": {
                        "workspace": "default",
                        "query": "incident review",
                        "retrieval_profile": "missing-profile",
                    },
                },
            }
        )

        self.assertEqual(result["error"]["code"], -32000)
        self.assertEqual(result["error"]["data"]["code"], "INVALID_REQUEST")
        self.assertIn("Unknown retrieval profile", result["error"]["message"])

    def test_search_health_tool(self):
        with patch.object(
            self.server.service,
            "search_health",
            return_value={
                "workspace": "default",
                "status": "pass",
                "readiness": {"workspace": "default", "status": "ready"},
                "benchmark": {
                    "corpus": "slack-corpus",
                    "mode": "hybrid",
                    "hit_at_3": 1.0,
                    "hit_at_10": 1.0,
                    "ndcg_at_k": 1.0,
                    "latency_ms_p95": 10.0,
                    "query_reports": [{"query": "incident review", "hit_at_3": True, "hit_at_10": True, "ndcg_at_k": 1.0, "latency_ms": 10.0}],
                },
                "benchmark_thresholds": {"min_hit_at_3": 0.5, "min_hit_at_10": 0.8, "min_ndcg_at_k": 0.6, "max_latency_p95_ms": 800.0},
                "degraded_queries": [],
                "failure_codes": [],
                "warning_codes": [],
            },
        ) as mock_health:
            result = self.server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 63,
                    "method": "tools/call",
                    "params": {
                        "name": "search.health",
                        "arguments": {"workspace": "default", "dataset_path": "docs/dev/benchmarks/slack_corpus_smoke.jsonl", "min_hit_at_10": 0.8, "min_ndcg_at_k": 0.6},
                    },
                }
            )

        self.assertIn('"status": "pass"', result["result"]["content"][0]["text"])
        mock_health.assert_called_once()

    def test_message_send_error_uses_structured_mcp_error(self):
        result = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "messages.send",
                    "arguments": {"workspace": "default", "text": "hello"},
                },
            }
        )

        self.assertEqual(result["error"]["code"], -32602)
        self.assertEqual(result["error"]["message"], "channel_ref is required")
        self.assertEqual(result["error"]["data"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(result["error"]["data"]["details"]["tool"], "messages.send")

    def test_unknown_tool_uses_method_not_found_error(self):
        result = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "nope.tool",
                    "arguments": {},
                },
            }
        )

        self.assertEqual(result["error"]["code"], -32601)
        self.assertEqual(result["error"]["data"]["code"], "METHOD_NOT_FOUND")

    def test_listener_ack_and_unregister_report_missing_ids(self):
        ack = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {
                    "name": "deliveries.ack",
                    "arguments": {"workspace": "default", "delivery_id": 999},
                },
            }
        )
        self.assertEqual(ack["error"]["data"]["code"], "NOT_FOUND")

        unregister = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "listeners.unregister",
                    "arguments": {"workspace": "default", "listener_id": 999},
                },
            }
        )
        self.assertEqual(unregister["error"]["data"]["code"], "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
