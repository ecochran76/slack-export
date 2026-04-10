import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from slack_mirror.service.api import create_api_server
from slack_mirror.service.app import get_app_service


class ApiServerTests(unittest.TestCase):
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
        self.server = create_api_server(bind="127.0.0.1", port=0, config_path=str(self.config_path))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._shutdown_server)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def _shutdown_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_health_workspaces_and_outbound_listener_flow(self):
        service = get_app_service(str(self.config_path))
        conn = service.connect()
        workspace_id = service.workspace_id(conn, "default")
        self.assertTrue(workspace_id > 0)
        conn.execute(
            """
            INSERT INTO users(workspace_id, user_id, username, display_name, real_name, email, is_bot, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (workspace_id, "UEGM25PMG", "ecochran", "Eric", "Eric Cochran", "", 0, "{}"),
        )
        conn.commit()

        with patch("slack_mirror.service.app.SlackApiClient") as mock_client_cls:
            client = mock_client_cls.return_value
            client.open_direct_message.return_value = {"ok": True, "channel": {"id": "D123"}}
            client.send_message.return_value = {"ok": True, "channel": "C123", "ts": "2000.1"}

            health = requests.get(f"{self.base_url}/v1/health", timeout=5)
            self.assertEqual(health.status_code, 200)
            self.assertTrue(health.json()["ok"])

            workspaces = requests.get(f"{self.base_url}/v1/workspaces", timeout=5)
            self.assertEqual(workspaces.status_code, 200)
            self.assertEqual(workspaces.json()["workspaces"][0]["name"], "default")

            listener = requests.post(
                f"{self.base_url}/v1/workspaces/default/listeners",
                json={"name": "hook", "event_types": ["message"], "channel_ids": ["C123"]},
                timeout=5,
            )
            self.assertEqual(listener.status_code, 201)
            listener_id = listener.json()["listener"]["id"]

            msg = requests.post(
                f"{self.base_url}/v1/workspaces/default/messages",
                json={"channel_ref": "@Eric", "text": "hello", "idempotency_key": "msg-1"},
                timeout=5,
            )
            self.assertEqual(msg.status_code, 200)
            self.assertEqual(msg.json()["action"]["status"], "sent")
            client.open_direct_message.assert_called_once_with(user_id="UEGM25PMG")
            self.assertEqual(client.send_message.call_count, 1)

        service.ingest_event(
            conn,
            workspace="default",
            event_id="evt-1",
            event_ts="2000.2",
            event_type="message",
            payload={"event": {"type": "message", "channel": "C123", "ts": "2000.2", "text": "hi"}},
        )

        deliveries = requests.get(f"{self.base_url}/v1/workspaces/default/deliveries", timeout=5)
        self.assertEqual(deliveries.status_code, 200)
        delivery_id = deliveries.json()["deliveries"][0]["id"]

        ack = requests.post(
            f"{self.base_url}/v1/workspaces/default/deliveries/{delivery_id}/ack",
            json={"status": "delivered"},
            timeout=5,
        )
        self.assertEqual(ack.status_code, 200)

        listener_status = requests.get(f"{self.base_url}/v1/workspaces/default/listeners/{listener_id}", timeout=5)
        self.assertEqual(listener_status.status_code, 200)
        self.assertEqual(listener_status.json()["listener"]["pending_deliveries"], 0)

        status = requests.get(f"{self.base_url}/v1/workspaces/default/status", timeout=5)
        self.assertEqual(status.status_code, 200)
        self.assertIn("summary", status.json())


if __name__ == "__main__":
    unittest.main()
