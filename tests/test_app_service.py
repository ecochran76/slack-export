import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from slack_mirror.core.db import connect, get_workspace_by_name, upsert_channel, upsert_derived_text, upsert_message, upsert_user, upsert_workspace
from slack_mirror.service.app import SlackMirrorAppService


class AppServiceTests(unittest.TestCase):
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
                    f"storage:",
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
        self.service = SlackMirrorAppService(str(self.config_path))
        self.conn = self.service.connect()

    def test_list_workspaces_uses_canonical_config(self):
        workspace_id = upsert_workspace(self.conn, name="default", team_id="T123", domain="example", config={"name": "default"})
        rows = self.service.list_workspaces(self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "default")
        self.assertEqual(workspace_id, int(rows[0]["id"]))

    def test_get_workspace_status_and_process_pending_events(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C123", "name": "general"})
        upsert_message(
            self.conn,
            workspace_id,
            "C123",
            {
                "ts": "1700000000.000100",
                "user": "U1",
                "text": "hello",
                "channel": "C123",
                "thread_ts": "1700000000.000100",
            },
        )

        summary, rows = self.service.get_workspace_status(self.conn, workspace="default")
        self.assertTrue(summary.healthy)
        self.assertEqual(summary.status, "HEALTHY")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].workspace, "default")
        self.assertEqual(rows[0].channel_class, "public")

        event_payload = {
            "event": {
                "type": "message",
                "channel": "C123",
                "ts": "1700000001.000200",
                "user": "U1",
                "text": "from event",
            }
        }
        self.service.ingest_event(
            self.conn,
            workspace="default",
            event_id="evt-1",
            event_ts="1700000001.000200",
            event_type="message",
            payload=event_payload,
        )
        result = self.service.process_pending_events(self.conn, workspace="default", limit=10)
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["errored"], 0)
        event_row = self.conn.execute(
            "SELECT status FROM events WHERE workspace_id = ? AND event_id = ?",
            (workspace_id, "evt-1"),
        ).fetchone()
        self.assertEqual(event_row["status"], "processed")

        ws_row = get_workspace_by_name(self.conn, "default")
        self.assertIsNotNone(ws_row)

    def test_search_health_reports_readiness_and_benchmark(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C123", "name": "general"})
        upsert_message(
            self.conn,
            workspace_id,
            "C123",
            {"ts": "1700000000.000100", "user": "U1", "text": "incident review follow-up", "channel": "C123"},
        )
        self.conn.execute(
            """
            INSERT INTO files(workspace_id, file_id, name, title, mimetype, local_path, raw_json)
            VALUES (?, 'F1', 'scan.pdf', 'Incident PDF', 'application/pdf', '/tmp/scan.pdf', '{}')
            """,
            (workspace_id,),
        )
        upsert_derived_text(
            self.conn,
            workspace_id=workspace_id,
            source_kind="file",
            source_id="F1",
            derivation_kind="ocr_text",
            extractor="tesseract_pdf",
            text="incident review appendix",
            media_type="application/pdf",
            local_path="/tmp/scan.pdf",
            metadata={"origin": "test"},
        )
        dataset = self.root / "search_eval.jsonl"
        dataset.write_text(
            '{"query":"incident review","relevant":{"C123:1700000000.000100":2,"file:F1:ocr_text:tesseract_pdf":2}}\n',
            encoding="utf-8",
        )

        health = self.service.search_health(
            self.conn,
            workspace="default",
            dataset_path=str(dataset),
            mode="hybrid",
            limit=10,
        )

        self.assertEqual(health["status"], "pass")
        self.assertEqual(health["readiness"]["status"], "ready")
        self.assertIsNotNone(health["benchmark"])
        self.assertGreaterEqual(health["benchmark"]["hit_at_3"], 0.5)

    def test_corpus_search_can_aggregate_all_workspaces(self):
        default_id = self.service.workspace_id(self.conn, "default")
        soylei_id = self.service.workspace_id(self.conn, "soylei")
        upsert_channel(self.conn, default_id, {"id": "C1", "name": "general"})
        upsert_channel(self.conn, soylei_id, {"id": "C2", "name": "ops"})
        upsert_user(self.conn, default_id, {"id": "U1", "name": "alice", "real_name": "Alice Example", "profile": {"display_name": "alice"}})
        upsert_user(self.conn, soylei_id, {"id": "U2", "name": "bob", "real_name": "Bob Example", "profile": {"display_name": "bob"}})
        upsert_message(self.conn, default_id, "C1", {"ts": "10.0", "text": "incident review default", "user": "U1"})
        upsert_message(self.conn, soylei_id, "C2", {"ts": "11.0", "text": "incident review soylei", "user": "U2"})

        rows = self.service.corpus_search(
            self.conn,
            all_workspaces=True,
            query="incident review",
            limit=10,
            mode="lexical",
        )

        workspaces = {row["workspace"] for row in rows}
        self.assertIn("default", workspaces)
        self.assertIn("soylei", workspaces)

    def test_send_message_and_thread_reply_are_audited(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C123", "name": "general"})

        with patch("slack_mirror.service.app.SlackApiClient") as mock_client_cls:
            client = mock_client_cls.return_value
            client.send_message.return_value = {"ok": True, "channel": "C123", "ts": "2000.0001"}
            client.send_thread_reply.return_value = {"ok": True, "channel": "C123", "ts": "2000.0002"}

            message_action = self.service.send_message(
                self.conn,
                workspace="default",
                channel_ref="general",
                text="hello world",
                options={"idempotency_key": "msg-1"},
            )
            reply_action = self.service.send_thread_reply(
                self.conn,
                workspace="default",
                channel_ref="general",
                thread_ref="2000.0001",
                text="reply text",
                options={"idempotency_key": "reply-1"},
            )

        self.assertEqual(message_action["status"], "sent")
        self.assertEqual(reply_action["status"], "sent")
        self.assertFalse(message_action["idempotent_replay"])
        self.assertFalse(reply_action["idempotent_replay"])
        self.assertFalse(message_action["retryable"])
        self.assertEqual(message_action["response"]["channel"], "C123")
        self.assertEqual(message_action["options"]["idempotency_key"], "msg-1")
        self.assertEqual(client.send_message.call_count, 1)
        self.assertEqual(client.send_thread_reply.call_count, 1)

        actions = self.conn.execute(
            "SELECT kind, channel_id, thread_ts, text, status, idempotency_key FROM outbound_actions ORDER BY id"
        ).fetchall()
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["kind"], "message")
        self.assertEqual(actions[0]["channel_id"], "C123")
        self.assertEqual(actions[0]["status"], "sent")
        self.assertEqual(actions[1]["kind"], "thread_reply")
        self.assertEqual(actions[1]["thread_ts"], "2000.0001")
        self.assertEqual(actions[1]["status"], "sent")

    def test_send_message_idempotency_returns_existing_action(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C123", "name": "general"})

        with patch("slack_mirror.service.app.SlackApiClient") as mock_client_cls:
            client = mock_client_cls.return_value
            client.send_message.return_value = {"ok": True, "channel": "C123", "ts": "2000.0001"}

            first = self.service.send_message(
                self.conn,
                workspace="default",
                channel_ref="general",
                text="dedupe me",
                options={"idempotency_key": "same-key"},
            )
            second = self.service.send_message(
                self.conn,
                workspace="default",
                channel_ref="general",
                text="dedupe me",
                options={"idempotency_key": "same-key"},
            )

        self.assertEqual(client.send_message.call_count, 1)
        self.assertEqual(first["status"], "sent")
        self.assertEqual(second["status"], "sent")
        self.assertEqual(first["id"], second["id"])
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(second["idempotent_replay"])
        self.assertFalse(second["retryable"])
        self.assertEqual(second["response"]["ts"], "2000.0001")

    def test_workspace_token_uses_outbound_config_for_write_actions(self):
        self.config_path.write_text(
            "\n".join(
                [
                    "version: 1",
                    "storage:",
                    f"  db_path: {self.db_path}",
                    "workspaces:",
                    "  - name: default",
                    "    team_id: T123",
                    "    token: xoxb-read-token",
                    "    outbound_token: xoxb-write-token",
                    "    user_token: xoxp-read-token",
                    "    outbound_user_token: xoxp-write-token",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        service = SlackMirrorAppService(str(self.config_path))
        self.assertEqual(service.workspace_token("default", auth_mode="bot", purpose="read"), "xoxb-read-token")
        self.assertEqual(service.workspace_token("default", auth_mode="bot", purpose="write"), "xoxb-write-token")
        self.assertEqual(service.workspace_token("default", auth_mode="user", purpose="write"), "xoxp-write-token")

    @patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-env-write-token"}, clear=False)
    def test_send_message_prefers_default_workspace_write_env_token(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C123", "name": "general"})

        with patch("slack_mirror.service.app.SlackApiClient") as mock_client_cls:
            client = mock_client_cls.return_value
            client.send_message.return_value = {"ok": True, "channel": "C123", "ts": "2000.0001"}

            action = self.service.send_message(
                self.conn,
                workspace="default",
                channel_ref="general",
                text="use env write token",
                options={"idempotency_key": "msg-env-token"},
            )

        self.assertEqual(action["status"], "sent")
        mock_client_cls.assert_called_once_with("xoxb-env-write-token")

    @patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-env-write-token"}, clear=False)
    def test_send_message_opens_dm_for_user_reference(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_user(
            self.conn,
            workspace_id,
            {
                "id": "UEGM25PMG",
                "name": "ecochran",
                "real_name": "Eric Cochran",
                "profile": {"display_name": "Eric"},
            },
        )

        with patch("slack_mirror.service.app.SlackApiClient") as mock_client_cls:
            client = mock_client_cls.return_value
            client.open_direct_message.return_value = {"ok": True, "channel": {"id": "D123"}}
            client.send_message.return_value = {"ok": True, "channel": "D123", "ts": "2000.0001"}

            action = self.service.send_message(
                self.conn,
                workspace="default",
                channel_ref="@Eric",
                text="hello Eric",
                options={"idempotency_key": "msg-dm-eric"},
            )

        self.assertEqual(action["status"], "sent")
        client.open_direct_message.assert_called_once_with(user_id="UEGM25PMG")
        client.send_message.assert_called_once_with(
            channel="D123",
            text="hello Eric",
            idempotency_key="msg-dm-eric",
        )

    @patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-env-write-token"}, clear=False)
    def test_send_message_fails_for_ambiguous_user_reference(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_user(
            self.conn,
            workspace_id,
            {
                "id": "UERIC1",
                "name": "ecochran",
                "real_name": "Eric Cochran",
                "profile": {"display_name": "Eric"},
            },
        )
        upsert_user(
            self.conn,
            workspace_id,
            {
                "id": "UERIC2",
                "name": "eric2",
                "real_name": "Eric Other",
                "profile": {"display_name": "Eric"},
            },
        )

        with patch("slack_mirror.service.app.SlackApiClient") as mock_client_cls:
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                self.service.send_message(
                    self.conn,
                    workspace="default",
                    channel_ref="@Eric",
                    text="hello Eric",
                    options={"idempotency_key": "msg-ambiguous-eric"},
                )
        mock_client_cls.return_value.open_direct_message.assert_not_called()

    @patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-env-write-token"}, clear=False)
    def test_idempotent_dm_send_skips_second_open_direct_message(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_user(
            self.conn,
            workspace_id,
            {
                "id": "UEGM25PMG",
                "name": "ecochran",
                "real_name": "Eric Cochran",
                "profile": {"display_name": "Eric"},
            },
        )

        with patch("slack_mirror.service.app.SlackApiClient") as mock_client_cls:
            client = mock_client_cls.return_value
            client.open_direct_message.return_value = {"ok": True, "channel": {"id": "D123"}}
            client.send_message.return_value = {"ok": True, "channel": "D123", "ts": "2000.0001"}

            first = self.service.send_message(
                self.conn,
                workspace="default",
                channel_ref="@Eric",
                text="hello Eric",
                options={"idempotency_key": "msg-dm-idempotent"},
            )
            second = self.service.send_message(
                self.conn,
                workspace="default",
                channel_ref="@Eric",
                text="hello Eric",
                options={"idempotency_key": "msg-dm-idempotent"},
            )

        self.assertEqual(first["id"], second["id"])
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(second["idempotent_replay"])
        client.open_direct_message.assert_called_once_with(user_id="UEGM25PMG")
        client.send_message.assert_called_once()

    def test_register_listener_and_queue_delivery(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C123", "name": "general"})
        listener = self.service.register_listener(
            self.conn,
            workspace="default",
            spec={
                "name": "message-hook",
                "event_types": ["message"],
                "channel_ids": ["C123"],
                "target": "local-process",
            },
        )
        self.assertEqual(listener["name"], "message-hook")

        self.service.ingest_event(
            self.conn,
            workspace="default",
            event_id="evt-1",
            event_ts="2000.0001",
            event_type="message",
            payload={"event": {"type": "message", "channel": "C123", "ts": "2000.0001", "text": "hi"}},
        )

        deliveries = self.service.list_listener_deliveries(self.conn, workspace="default")
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0]["status"], "pending")
        self.assertEqual(deliveries[0]["event_type"], "message")

        status = self.service.get_listener_status(self.conn, workspace="default", listener_id=int(listener["id"]))
        self.assertEqual(status["pending_deliveries"], 1)

        self.service.ack_listener_delivery(self.conn, workspace="default", delivery_id=int(deliveries[0]["id"]))
        acked = self.service.list_listener_deliveries(self.conn, workspace="default", status="delivered")
        self.assertEqual(len(acked), 1)

    def test_listener_register_upserts_and_failed_ack_is_recorded(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C123", "name": "general"})
        first = self.service.register_listener(
            self.conn,
            workspace="default",
            spec={"name": "hook", "event_types": ["message"], "channel_ids": ["C123"], "target": "worker-a"},
        )
        second = self.service.register_listener(
            self.conn,
            workspace="default",
            spec={"name": "hook", "event_types": ["reaction_added"], "channel_ids": [], "target": "worker-b"},
        )
        self.assertEqual(first["id"], second["id"])
        listeners = self.service.list_listeners(self.conn, workspace="default")
        self.assertEqual(len(listeners), 1)
        self.assertIn("reaction_added", listeners[0]["event_types_json"])
        self.assertEqual(listeners[0]["target"], "worker-b")

        self.service.ingest_event(
            self.conn,
            workspace="default",
            event_id="evt-2",
            event_ts="2000.0003",
            event_type="reaction_added",
            payload={"event": {"type": "reaction_added", "channel": "C123", "ts": "2000.0003"}},
        )
        deliveries = self.service.list_listener_deliveries(self.conn, workspace="default")
        self.assertEqual(len(deliveries), 1)
        delivery_id = int(deliveries[0]["id"])

        self.service.ack_listener_delivery(
            self.conn,
            workspace="default",
            delivery_id=delivery_id,
            status="failed",
            error="consumer exploded",
        )
        failed = self.service.list_listener_deliveries(self.conn, workspace="default", status="failed")
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["attempts"], 1)
        self.assertEqual(failed[0]["error"], "consumer exploded")

    def test_listener_ack_and_unregister_fail_for_missing_ids(self):
        self.service.workspace_id(self.conn, "default")
        with self.assertRaisesRegex(ValueError, "Delivery '999' not found"):
            self.service.ack_listener_delivery(self.conn, workspace="default", delivery_id=999)
        with self.assertRaisesRegex(ValueError, "Listener '999' not found"):
            self.service.unregister_listener(self.conn, workspace="default", listener_id=999)


if __name__ == "__main__":
    unittest.main()
