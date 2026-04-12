import json
import tempfile
import threading
import unittest
from importlib import util as importlib_util
from pathlib import Path
from unittest.mock import patch

import requests

from slack_mirror.service.api import create_api_server
from slack_mirror.service.app import LiveValidationResult, get_app_service

EXPORT_DOCX_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export_channel_day_docx.py"


def _load_export_docx_module():
    spec = importlib_util.spec_from_file_location("export_channel_day_docx", EXPORT_DOCX_SCRIPT)
    module = importlib_util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


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
                    "  - name: soylei",
                    "    team_id: T456",
                    "    token: xoxb-soylei-token",
                    "    user_token: xoxp-soylei-token",
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
            self.assertFalse(msg.json()["action"]["idempotent_replay"])
            self.assertFalse(msg.json()["action"]["retryable"])
            client.open_direct_message.assert_called_once_with(user_id="UEGM25PMG")
            self.assertEqual(client.send_message.call_count, 1)

            replay = requests.post(
                f"{self.base_url}/v1/workspaces/default/messages",
                json={"channel_ref": "@Eric", "text": "hello", "idempotency_key": "msg-1"},
                timeout=5,
            )
            self.assertEqual(replay.status_code, 200)
            self.assertTrue(replay.json()["action"]["idempotent_replay"])
            self.assertFalse(replay.json()["action"]["retryable"])

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

    def test_runtime_live_validation_endpoint(self):
        with patch(
            "slack_mirror.service.api.get_app_service"
        ) as mock_get_service:
            service = mock_get_service.return_value
            service.validate_live_runtime.return_value = LiveValidationResult(
                ok=False,
                status="fail",
                require_live_units=True,
                summary="Summary: FAIL (1 failure)",
                lines=["FAIL [EVENT_ERRORS] workspace default has event errors: 1"],
                exit_code=1,
                failure_count=1,
                warning_count=0,
                failure_codes=["EVENT_ERRORS"],
                warning_codes=[],
                workspaces=[
                    {
                        "name": "default",
                        "event_errors": 1,
                        "embedding_errors": 0,
                        "event_pending": 0,
                        "embedding_pending": 0,
                        "failure_codes": ["EVENT_ERRORS"],
                        "warning_codes": [],
                    }
                ],
            )
            server = create_api_server(bind="127.0.0.1", port=0, config_path=str(self.config_path))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            self.addCleanup(thread.join, 2)
            base_url = f"http://127.0.0.1:{server.server_address[1]}"

            resp = requests.get(f"{base_url}/v1/runtime/live-validation", timeout=5)
            self.assertEqual(resp.status_code, 503)
            self.assertFalse(resp.json()["ok"])
            self.assertEqual(resp.json()["validation"]["status"], "fail")
            self.assertEqual(resp.json()["validation"]["failure_codes"], ["EVENT_ERRORS"])
            self.assertEqual(resp.json()["validation"]["workspaces"][0]["name"], "default")
            service.validate_live_runtime.assert_called_once_with(require_live_units=True)

    def test_export_file_serving_endpoint(self):
        exports_root = self.root / "exports-root"
        bundle_dir = exports_root / "channel-day-default-general-2026-04-12-abc123"
        attachment_dir = bundle_dir / "attachments" / "incident"
        attachment_dir.mkdir(parents=True)
        (attachment_dir / "report.pdf").write_bytes(b"%PDF-1.4\n")
        (attachment_dir / "preview.txt").write_text("preview body\n", encoding="utf-8")
        (attachment_dir / "archive.bin").write_bytes(b"\x00\x01")
        docx_input = bundle_dir / "channel-day.json"
        docx_path = attachment_dir / "sample.docx"
        docx_input.write_text(
            json.dumps(
                {
                    "workspace": "default",
                    "channel": "general",
                    "channel_id": "C123",
                    "day": "2026-04-12",
                    "tz": "America/Chicago",
                    "messages": [
                        {
                            "ts": "1.0",
                            "human_ts": "2026-04-12 10:00:00 CDT",
                            "user_id": "U123",
                            "user_label": "Eric (U123)",
                            "text": "DOCX preview body",
                            "thread_ts": None,
                            "deleted": False,
                            "attachments": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        _load_export_docx_module().render_channel_day_docx(docx_input, docx_path)

        config_text = self.config_path.read_text(encoding="utf-8")
        self.config_path.write_text(
            config_text
            + "\n".join(
                [
                    "exports:",
                    f"  root_dir: {exports_root}",
                    "  local_base_url: http://slack.localhost",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        server = create_api_server(bind="127.0.0.1", port=0, config_path=str(self.config_path))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        ok = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/report.pdf",
            timeout=5,
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.headers["content-type"], "application/pdf")
        self.assertEqual(ok.content, b"%PDF-1.4\n")

        preview = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/report.pdf/preview",
            timeout=5,
        )
        self.assertEqual(preview.status_code, 200)
        self.assertIn("text/html", preview.headers["content-type"])
        self.assertIn("/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/report.pdf", preview.text)
        self.assertIn("<iframe", preview.text)

        text_preview = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/preview.txt/preview",
            timeout=5,
        )
        self.assertEqual(text_preview.status_code, 200)
        self.assertIn("preview body", text_preview.text)
        self.assertIn("<pre", text_preview.text)

        docx_preview = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/sample.docx/preview",
            timeout=5,
        )
        self.assertEqual(docx_preview.status_code, 200)
        self.assertIn("DOCX preview body", docx_preview.text)
        self.assertIn("<article", docx_preview.text)

        unsupported = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/archive.bin/preview",
            timeout=5,
        )
        self.assertEqual(unsupported.status_code, 415)
        self.assertEqual(unsupported.json()["error"]["code"], "PREVIEW_UNSUPPORTED")

    def test_search_endpoints(self):
        with patch("slack_mirror.service.api.get_app_service") as mock_get_service:
            service = mock_get_service.return_value
            service.connect.return_value = object()
            service.corpus_search.return_value = [
                {
                    "result_kind": "derived_text",
                    "source_label": "Incident PDF",
                    "text": "incident review appendix",
                    "_source": "hybrid",
                    "_hybrid_score": 4.2,
                }
            ]
            service.search_readiness.return_value = {
                "workspace": "default",
                "status": "ready",
                "messages": {"count": 10, "embeddings": {"count": 10, "pending": 0, "errors": 0}},
                "derived_text": {
                    "attachment_text": {"count": 4, "pending": 0, "errors": 0},
                    "ocr_text": {"count": 2, "pending": 0, "errors": 0},
                },
            }
            service.search_health.return_value = {
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
            }

            server = create_api_server(bind="127.0.0.1", port=0, config_path=str(self.config_path))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            self.addCleanup(thread.join, 2)
            base_url = f"http://127.0.0.1:{server.server_address[1]}"

            corpus = requests.get(
                f"{base_url}/v1/workspaces/default/search/corpus",
                params={"query": "incident review", "mode": "hybrid", "kind": "ocr_text", "source_kind": "file"},
                timeout=5,
            )
            self.assertEqual(corpus.status_code, 200)
            self.assertTrue(corpus.json()["ok"])
            self.assertEqual(corpus.json()["results"][0]["result_kind"], "derived_text")

            all_corpus = requests.get(
                f"{base_url}/v1/search/corpus",
                params={"query": "incident review", "mode": "hybrid"},
                timeout=5,
            )
            self.assertEqual(all_corpus.status_code, 200)
            self.assertEqual(all_corpus.json()["scope"], "all")
            self.assertTrue(all_corpus.json()["ok"])
            self.assertEqual(service.corpus_search.call_count, 2)

            readiness = requests.get(f"{base_url}/v1/workspaces/default/search/readiness", timeout=5)
            self.assertEqual(readiness.status_code, 200)
            self.assertEqual(readiness.json()["readiness"]["status"], "ready")
            service.search_readiness.assert_called_once()

            health = requests.get(
                f"{base_url}/v1/workspaces/default/search/health",
                params={"dataset": "docs/dev/benchmarks/slack_corpus_smoke.jsonl", "min_hit_at_10": "0.8", "min_ndcg_at_k": "0.6"},
                timeout=5,
            )
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["health"]["status"], "pass")
            service.search_health.assert_called_once()

    def test_message_send_uses_structured_error_envelope(self):
        resp = requests.post(
            f"{self.base_url}/v1/workspaces/default/messages",
            json={"text": "hello"},
            timeout=5,
        )

        self.assertEqual(resp.status_code, 400)
        payload = resp.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(payload["error"]["message"], "channel_ref is required")
        self.assertFalse(payload["error"]["retryable"])
        self.assertEqual(payload["error"]["details"]["operation"], "messages.send")
        self.assertEqual(payload["error"]["details"]["workspace"], "default")

    def test_message_send_reports_not_found_workspace(self):
        resp = requests.post(
            f"{self.base_url}/v1/workspaces/missing/messages",
            json={"channel_ref": "C123", "text": "hello"},
            timeout=5,
        )

        self.assertEqual(resp.status_code, 404)
        payload = resp.json()
        self.assertEqual(payload["error"]["code"], "NOT_FOUND")
        self.assertEqual(payload["error"]["details"]["workspace"], "missing")

    def test_listener_ack_and_unregister_report_missing_ids(self):
        ack = requests.post(
            f"{self.base_url}/v1/workspaces/default/deliveries/999/ack",
            json={"status": "delivered"},
            timeout=5,
        )
        self.assertEqual(ack.status_code, 404)
        self.assertEqual(ack.json()["error"]["code"], "NOT_FOUND")

        delete = requests.delete(
            f"{self.base_url}/v1/workspaces/default/listeners/999",
            timeout=5,
        )
        self.assertEqual(delete.status_code, 404)
        self.assertEqual(delete.json()["error"]["code"], "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
