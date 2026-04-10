import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class _BufferStream:
    def __init__(self, initial: bytes = b""):
        self.buffer = io.BytesIO(initial)


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
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.server = SlackMirrorMcpServer(str(self.config_path))

    def test_initialize_and_tools_list(self):
        init = self.server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "slack-mirror")
        self.assertIn("tools", init["result"]["capabilities"])

        tools = self.server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = [tool["name"] for tool in tools["result"]["tools"]]
        self.assertIn("health", names)
        self.assertIn("runtime.live_validation", names)
        self.assertIn("messages.send", names)
        self.assertIn("listeners.register", names)

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


if __name__ == "__main__":
    unittest.main()
