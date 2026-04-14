import json
import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from importlib import util as importlib_util
from pathlib import Path
from types import SimpleNamespace
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
                    "exports:",
                    "  local_base_url: http://slack.localhost",
                    "  external_base_url: https://slack.example.test",
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

    def test_workspace_channels_endpoint_and_exports_picker_ui(self):
        service = get_app_service(str(self.config_path))
        conn = service.connect()
        workspace_id = service.workspace_id(conn, "default")

        from slack_mirror.core.db import upsert_channel, upsert_message

        upsert_channel(conn, workspace_id, {"id": "C123", "name": "general", "is_private": False})
        upsert_message(
            conn,
            workspace_id,
            "C123",
            {
                "ts": "1712870400.000100",
                "user": "U1",
                "text": "hello",
                "channel": "C123",
            },
        )

        channels = requests.get(f"{self.base_url}/v1/workspaces/default/channels", timeout=5)
        self.assertEqual(channels.status_code, 200)
        self.assertTrue(channels.json()["ok"])
        self.assertEqual(channels.json()["channels"][0]["name"], "general")
        self.assertEqual(channels.json()["channels"][0]["latest_message_day"], "2024-04-11")

        exports_index = requests.get(f"{self.base_url}/exports", timeout=5)
        self.assertEqual(exports_index.status_code, 200)
        self.assertIn("export-workspace", exports_index.text)
        self.assertIn("export-channel-filter", exports_index.text)
        self.assertIn("Search by name, id, or class", exports_index.text)
        self.assertIn("export-channel-filter-meta", exports_index.text)
        self.assertIn("export-channel", exports_index.text)
        self.assertIn("/v1/workspaces", exports_index.text)
        self.assertIn("/channels", exports_index.text)
        self.assertIn("Loading workspaces", exports_index.text)
        self.assertIn("channelSearchText", exports_index.text)
        self.assertIn("No channels match this filter", exports_index.text)
        self.assertIn("mirrored channels match", exports_index.text)

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

    def test_runtime_status_endpoint(self):
        with patch(
            "slack_mirror.service.api.get_app_service"
        ) as mock_get_service:
            service = mock_get_service.return_value
            service.runtime_status.return_value = SimpleNamespace(
                ok=True,
                wrappers_present=True,
                api_service_present=True,
                config_present=True,
                db_present=True,
                cache_present=True,
                rollback_snapshot_present=True,
                services={"slack-mirror-api.service": "active"},
                reconcile_workspaces=[
                    {
                        "name": "default",
                        "state_present": True,
                        "auth_mode": "user",
                        "downloaded": 2,
                        "warnings": 0,
                        "failed": 0,
                        "attempted": 2,
                        "age_seconds": 12.0,
                        "iso_utc": "2026-04-13T01:35:09+00:00",
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

            resp = requests.get(f"{base_url}/v1/runtime/status", timeout=5)
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.json()["ok"])
            self.assertTrue(resp.json()["status"]["wrappers_present"])
            self.assertEqual(resp.json()["status"]["services"]["slack-mirror-api.service"], "active")
            self.assertEqual(resp.json()["status"]["reconcile_workspaces"][0]["name"], "default")
            service.runtime_status.assert_called_once_with()

    def test_runtime_reports_endpoints(self):
        report_dir = self.db_path.parent / "runtime-reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "morning-ops.latest.html").write_text("<html><body>runtime report</body></html>", encoding="utf-8")
        (report_dir / "morning-ops.latest.md").write_text("# runtime report\n", encoding="utf-8")
        (report_dir / "morning-ops.latest.json").write_text(
            json.dumps(
                {
                    "name": "morning-ops",
                    "base_url": "http://slack.localhost",
                    "fetched_at": "2026-04-13T12:00:00+00:00",
                    "status": "pass",
                    "summary": "Summary: PASS",
                    "markdown_path": str(report_dir / "morning-ops-20260413T120000Z.md"),
                    "html_path": str(report_dir / "morning-ops-20260413T120000Z.html"),
                    "latest_markdown_path": str(report_dir / "morning-ops.latest.md"),
                    "latest_html_path": str(report_dir / "morning-ops.latest.html"),
                    "latest_json_path": str(report_dir / "morning-ops.latest.json"),
                }
            ),
            encoding="utf-8",
        )

        listing = requests.get(f"{self.base_url}/v1/runtime/reports", timeout=5)
        self.assertEqual(listing.status_code, 200)
        self.assertTrue(listing.json()["ok"])
        self.assertEqual(listing.json()["reports"][0]["name"], "morning-ops")
        self.assertEqual(listing.json()["reports"][0]["html_url"], "/runtime/reports/morning-ops")
        self.assertEqual(listing.json()["reports"][0]["markdown_url"], "/runtime/reports/morning-ops.latest.md")
        self.assertEqual(listing.json()["reports"][0]["json_url"], "/runtime/reports/morning-ops.latest.json")

        detail = requests.get(f"{self.base_url}/v1/runtime/reports/morning-ops", timeout=5)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["report"]["name"], "morning-ops")
        self.assertEqual(detail.json()["report"]["html_url"], "/runtime/reports/morning-ops")

        latest_detail = requests.get(f"{self.base_url}/v1/runtime/reports/latest", timeout=5)
        self.assertEqual(latest_detail.status_code, 200)
        self.assertEqual(latest_detail.json()["report"]["name"], "morning-ops")

        latest_html = requests.get(f"{self.base_url}/runtime/reports/morning-ops", timeout=5)
        self.assertEqual(latest_html.status_code, 200)
        self.assertIn("runtime report", latest_html.text)
        self.assertIn("text/html", latest_html.headers["content-type"])

        latest_alias_html = requests.get(f"{self.base_url}/runtime/reports/latest", timeout=5)
        self.assertEqual(latest_alias_html.status_code, 200)
        self.assertIn("runtime report", latest_alias_html.text)

        latest_json = requests.get(f"{self.base_url}/runtime/reports/morning-ops.latest.json", timeout=5)
        self.assertEqual(latest_json.status_code, 200)
        self.assertEqual(latest_json.json()["name"], "morning-ops")

        index_html = requests.get(f"{self.base_url}/runtime/reports", timeout=5)
        self.assertEqual(index_html.status_code, 200)
        self.assertIn("Slack Mirror Runtime Reports", index_html.text)
        self.assertIn("Create runtime report", index_html.text)
        self.assertIn("create-report-button", index_html.text)
        self.assertIn("report-base-url-select", index_html.text)
        self.assertIn("http://slack.localhost", index_html.text)
        self.assertIn("https://slack.example.test", index_html.text)
        self.assertIn("data-report-name-preset='morning-ops'", index_html.text)
        self.assertIn("timestamped-report-name", index_html.text)
        self.assertIn("data-report-rename-toggle='morning-ops'", index_html.text)
        self.assertIn("id='report-row-morning-ops'", index_html.text)
        self.assertIn("rename-row-morning-ops", index_html.text)
        self.assertIn("rename-input-morning-ops", index_html.text)
        self.assertIn("data-report-delete='morning-ops'", index_html.text)
        self.assertIn("/runtime/reports/latest", index_html.text)
        self.assertIn("/v1/runtime/reports/latest", index_html.text)
        self.assertIn("/runtime/reports/morning-ops.latest.json", index_html.text)
        self.assertIn("latest</span>", index_html.text)
        self.assertIn("latest-row", index_html.text)
        self.assertIn("data-report-rename-save='morning-ops'", index_html.text)
        self.assertIn("data-report-rename-cancel='morning-ops'", index_html.text)
        self.assertIn("insertCreatedReport(", index_html.text)
        self.assertIn("reportRowHtml(", index_html.text)
        self.assertIn("bindInlineManagerActions(", index_html.text)
        self.assertIn("setInlineManagerBusyState(", index_html.text)
        self.assertIn("button.dataset.busy==='true'", index_html.text)
        self.assertIn("Created runtime report", index_html.text)
        self.assertIn("applyReportRename(", index_html.text)
        self.assertIn("removeReportRow(", index_html.text)
        self.assertIn("report-empty-row", index_html.text)
        self.assertIn("ensureReportEmptyStateRow(", index_html.text)
        self.assertIn("itemLabel:'runtime report'", index_html.text)
        self.assertNotIn(
            "if(resp.ok){window.location.reload();return;}const data=await resp.json().catch(()=>({error:{message:'Create failed'}}));",
            index_html.text,
        )
        self.assertNotIn(
            "if(resp.ok){window.location.reload();return;}const data=await resp.json().catch(()=>({error:{message:'Rename failed'}}));",
            index_html.text,
        )
        self.assertNotIn(
            "if(resp.ok){window.location.reload();return;}const data=await resp.json().catch(()=>({error:{message:'Delete failed'}}));",
            index_html.text,
        )

    def test_runtime_reports_endpoint_rejects_invalid_names(self):
        resp = requests.get(f"{self.base_url}/v1/runtime/reports/bad%20name", timeout=5)
        self.assertEqual(resp.status_code, 400)
        missing = requests.get(f"{self.base_url}/runtime/reports/bad%20name", timeout=5)
        self.assertEqual(missing.status_code, 400)

    def test_runtime_reports_crud_endpoints(self):
        service = get_app_service(str(self.config_path))
        created_payload = {
            "name": "daily-ops",
            "base_url": "http://slack.localhost",
            "fetched_at": "2026-04-13T12:00:00+00:00",
            "status": "pass",
            "summary": "Summary: PASS",
            "markdown_path": str(self.root / "daily-ops-20260413T120000Z.md"),
            "html_path": str(self.root / "daily-ops-20260413T120000Z.html"),
            "latest_markdown_path": str(self.root / "daily-ops.latest.md"),
            "latest_html_path": str(self.root / "daily-ops.latest.html"),
            "latest_json_path": str(self.root / "daily-ops.latest.json"),
        }
        renamed_payload = {**created_payload, "name": "daily-ops-renamed"}
        with patch.object(service, "create_runtime_report", return_value=created_payload) as mock_create, patch.object(
            service, "rename_runtime_report", return_value=renamed_payload
        ) as mock_rename, patch.object(service, "delete_runtime_report", return_value=True) as mock_delete, patch(
            "slack_mirror.service.api.get_app_service", return_value=service
        ):
            server = create_api_server(bind="127.0.0.1", port=0, config_path=str(self.config_path))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            self.addCleanup(thread.join, 2)
            base_url = f"http://127.0.0.1:{server.server_address[1]}"

            created = requests.post(
                f"{base_url}/v1/runtime/reports",
                headers={"Origin": base_url},
                json={"base_url": "http://slack.localhost", "name": "daily-ops"},
                timeout=5,
            )
            self.assertEqual(created.status_code, 201)
            self.assertEqual(created.json()["report"]["name"], "daily-ops")
            self.assertEqual(created.json()["report"]["html_url"], "/runtime/reports/daily-ops")
            mock_create.assert_called_once_with(base_url="http://slack.localhost", name="daily-ops", timeout=5.0)

            renamed = requests.post(
                f"{base_url}/v1/runtime/reports/daily-ops/rename",
                headers={"Origin": base_url},
                json={"name": "daily-ops-renamed"},
                timeout=5,
            )
            self.assertEqual(renamed.status_code, 200)
            self.assertEqual(renamed.json()["report"]["name"], "daily-ops-renamed")
            self.assertEqual(renamed.json()["report"]["html_url"], "/runtime/reports/daily-ops-renamed")
            mock_rename.assert_called_once_with(name="daily-ops", new_name="daily-ops-renamed")

            deleted = requests.delete(
                f"{base_url}/v1/runtime/reports/daily-ops-renamed",
                headers={"Origin": base_url},
                timeout=5,
            )
            self.assertEqual(deleted.status_code, 200)
            self.assertTrue(deleted.json()["deleted"])
            self.assertEqual(deleted.json()["name"], "daily-ops-renamed")
            mock_delete.assert_called_once_with(name="daily-ops-renamed")

    def test_export_crud_endpoints(self):
        service = get_app_service(str(self.config_path))
        created_payload = {
            "export_id": "channel-day-default-general-2026-04-12-abc123",
            "bundle_url": "http://slack.localhost/exports/channel-day-default-general-2026-04-12-abc123",
            "files": [],
        }
        renamed_payload = {
            **created_payload,
            "export_id": "channel-day-default-general-renamed",
            "bundle_url": "http://slack.localhost/exports/channel-day-default-general-renamed",
        }
        with patch.object(service, "create_channel_day_export", return_value=created_payload) as mock_create, patch.object(
            service, "rename_export", return_value=renamed_payload
        ) as mock_rename, patch.object(service, "delete_export", return_value=True) as mock_delete, patch(
            "slack_mirror.service.api.get_app_service", return_value=service
        ):
            server = create_api_server(bind="127.0.0.1", port=0, config_path=str(self.config_path))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            self.addCleanup(thread.join, 2)
            base_url = f"http://127.0.0.1:{server.server_address[1]}"

            created = requests.post(
                f"{base_url}/v1/exports",
                headers={"Origin": base_url},
                json={
                    "kind": "channel-day",
                    "workspace": "default",
                    "channel": "general",
                    "day": "2026-04-12",
                    "audience": "local",
                },
                timeout=5,
            )
            self.assertEqual(created.status_code, 201)
            self.assertEqual(created.json()["export"]["export_id"], "channel-day-default-general-2026-04-12-abc123")
            mock_create.assert_called_once_with(
                workspace="default",
                channel="general",
                day="2026-04-12",
                tz="America/Chicago",
                audience="local",
                export_id=None,
            )

            renamed = requests.post(
                f"{base_url}/v1/exports/channel-day-default-general-2026-04-12-abc123/rename",
                headers={"Origin": base_url},
                json={"export_id": "channel-day-default-general-renamed", "audience": "local"},
                timeout=5,
            )
            self.assertEqual(renamed.status_code, 200)
            self.assertEqual(renamed.json()["export"]["export_id"], "channel-day-default-general-renamed")
            mock_rename.assert_called_once_with(
                export_id="channel-day-default-general-2026-04-12-abc123",
                new_export_id="channel-day-default-general-renamed",
                audience="local",
            )

            deleted = requests.delete(
                f"{base_url}/v1/exports/channel-day-default-general-renamed",
                headers={"Origin": base_url},
                timeout=5,
            )
            self.assertEqual(deleted.status_code, 200)
            self.assertTrue(deleted.json()["deleted"])
            self.assertEqual(deleted.json()["export_id"], "channel-day-default-general-renamed")
            mock_delete.assert_called_once_with(export_id="channel-day-default-general-renamed")

    def test_frontend_auth_protects_runtime_reports_and_supports_local_login(self):
        report_dir = self.db_path.parent / "runtime-reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        exports_root = self.root / "exports-root"
        bundle_dir = exports_root / "channel-day-default-general-2026-04-12-abc123"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        (bundle_dir / "index.html").write_text("<html><body><h1>protected export</h1></body></html>", encoding="utf-8")
        (report_dir / "morning-ops.latest.html").write_text("<html><body>runtime report</body></html>", encoding="utf-8")
        (report_dir / "morning-ops.latest.md").write_text("# runtime report\n", encoding="utf-8")
        (report_dir / "morning-ops.latest.json").write_text(
            json.dumps(
                {
                    "name": "morning-ops",
                    "base_url": "http://slack.localhost",
                    "fetched_at": "2026-04-13T12:00:00+00:00",
                    "status": "pass",
                    "summary": "Summary: PASS",
                    "latest_markdown_path": str(report_dir / "morning-ops.latest.md"),
                    "latest_html_path": str(report_dir / "morning-ops.latest.html"),
                    "latest_json_path": str(report_dir / "morning-ops.latest.json"),
                }
            ),
            encoding="utf-8",
        )

        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8")
            + "\n".join(
                [
                    "exports:",
                    "  external_base_url: https://slack.ecochran.dyndns.org",
                    "service:",
                    "  auth:",
                    "    enabled: true",
                    "    allow_registration: true",
                    "    cookie_secure_mode: never",
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

        html_redirect = requests.get(f"{base_url}/runtime/reports", timeout=5, allow_redirects=False)
        self.assertEqual(html_redirect.status_code, 303)
        self.assertIn("/login?next=%2Fruntime%2Freports&reason=auth_required", html_redirect.headers["location"])

        root_redirect = requests.get(f"{base_url}/", timeout=5, allow_redirects=False)
        self.assertEqual(root_redirect.status_code, 303)
        self.assertEqual(root_redirect.headers["location"], "/login?next=%2F&reason=auth_required")

        settings_redirect = requests.get(f"{base_url}/settings", timeout=5, allow_redirects=False)
        self.assertEqual(settings_redirect.status_code, 303)
        self.assertEqual(settings_redirect.headers["location"], "/login?next=%2Fsettings&reason=auth_required")

        export_redirect = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123",
            timeout=5,
            allow_redirects=False,
        )
        self.assertEqual(export_redirect.status_code, 303)
        self.assertIn("/login?next=%2Fexports%2Fchannel-day-default-general-2026-04-12-abc123&reason=auth_required", export_redirect.headers["location"])

        api_blocked = requests.get(f"{base_url}/v1/runtime/reports", timeout=5)
        self.assertEqual(api_blocked.status_code, 401)
        self.assertEqual(api_blocked.json()["error"]["code"], "AUTH_REQUIRED")

        login_page = requests.get(f"{base_url}/login", timeout=5)
        self.assertEqual(login_page.status_code, 200)
        self.assertIn("Slack Mirror", login_page.text)
        self.assertIn("Email or username", login_page.text)

        login_reason_page = requests.get(f"{base_url}/login?next=%2Fsettings&reason=auth_required", timeout=5)
        self.assertEqual(login_reason_page.status_code, 200)
        self.assertIn("Sign in to continue to the protected page you requested.", login_reason_page.text)

        register_page = requests.get(f"{base_url}/register", timeout=5)
        self.assertEqual(register_page.status_code, 200)
        self.assertIn("Create access", register_page.text)
        self.assertIn("Username", register_page.text)

        session = requests.Session()
        registered = session.post(
            f"{base_url}/auth/register",
            json={"username": "eric", "display_name": "Eric", "password": "correct-horse-123"},
            headers={"origin": base_url},
            timeout=5,
        )
        self.assertEqual(registered.status_code, 201)
        self.assertTrue(registered.json()["session"]["authenticated"])
        self.assertEqual(registered.json()["session"]["username"], "eric")

        auth_session = session.get(f"{base_url}/auth/session", timeout=5)
        self.assertEqual(auth_session.status_code, 200)
        self.assertTrue(auth_session.json()["session"]["authenticated"])
        self.assertEqual(auth_session.json()["session"]["username"], "eric")
        current_session_id = auth_session.json()["session"]["session_id"]

        sessions_listing = session.get(f"{base_url}/auth/sessions", timeout=5)
        self.assertEqual(sessions_listing.status_code, 200)
        self.assertTrue(sessions_listing.json()["ok"])
        self.assertEqual(sessions_listing.json()["sessions"][0]["session_id"], current_session_id)
        self.assertTrue(sessions_listing.json()["sessions"][0]["active"])

        landing = session.get(f"{base_url}/", timeout=5)
        self.assertEqual(landing.status_code, 200)
        self.assertIn("Authenticated workspace home", landing.text)
        self.assertIn("Signed in as <strong>Eric</strong>", landing.text)
        self.assertIn("/runtime/reports/latest", landing.text)
        self.assertIn("/settings", landing.text)
        self.assertIn("/exports/channel-day-default-general-2026-04-12-abc123", landing.text)
        self.assertIn("/v1/exports", landing.text)

        settings = session.get(f"{base_url}/settings", timeout=5)
        self.assertEqual(settings.status_code, 200)
        self.assertIn("Account settings", settings.text)
        self.assertIn("Signed in as <strong>Eric</strong>", settings.text)
        self.assertIn("Auth governance", settings.text)
        self.assertIn("Session lifetime", settings.text)
        self.assertIn("Idle timeout", settings.text)
        self.assertIn("Login throttle", settings.text)
        self.assertIn("/auth/sessions", settings.text)
        self.assertIn("Session API", settings.text)
        self.assertIn("Sign out here", settings.text)
        self.assertNotIn("window.location.reload()", settings.text)
        self.assertIn("markSessionInactive", settings.text)
        self.assertIn("reason:'session_revoked'", settings.text)

        allowed = session.get(f"{base_url}/runtime/reports/latest", timeout=5)
        self.assertEqual(allowed.status_code, 200)
        self.assertIn("runtime report", allowed.text)

        allowed_export = session.get(f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123", timeout=5)
        self.assertEqual(allowed_export.status_code, 200)
        self.assertIn("protected export", allowed_export.text)

        allowed_api = session.get(f"{base_url}/v1/runtime/reports/latest", timeout=5)
        self.assertEqual(allowed_api.status_code, 200)
        self.assertEqual(allowed_api.json()["report"]["name"], "morning-ops")

        missing_revoke = session.post(
            f"{base_url}/auth/sessions/999999/revoke",
            json={},
            headers={"origin": base_url},
            timeout=5,
        )
        self.assertEqual(missing_revoke.status_code, 404)

        revoke_current = session.post(
            f"{base_url}/auth/sessions/{current_session_id}/revoke",
            json={},
            headers={"origin": base_url},
            timeout=5,
        )
        self.assertEqual(revoke_current.status_code, 200)
        self.assertTrue(revoke_current.json()["revoked"])
        blocked_again = session.get(f"{base_url}/v1/runtime/reports/latest", timeout=5)
        self.assertEqual(blocked_again.status_code, 401)

        logged_out = requests.get(f"{base_url}/logout", timeout=5, allow_redirects=False)
        self.assertEqual(logged_out.status_code, 303)
        self.assertEqual(logged_out.headers["location"], "/login?next=%2F&reason=signed_out")

        signed_out_page = requests.get(f"{base_url}/login?next=%2F&reason=signed_out", timeout=5)
        self.assertEqual(signed_out_page.status_code, 200)
        self.assertIn("You have been signed out.", signed_out_page.text)

        bad_origin_register = requests.post(
            f"{base_url}/auth/register",
            json={"username": "mallory", "display_name": "Mallory", "password": "correct-horse-123"},
            headers={"origin": "https://evil.example"},
            timeout=5,
        )
        self.assertEqual(bad_origin_register.status_code, 403)
        self.assertEqual(bad_origin_register.json()["error"]["code"], "CSRF_FAILED")

        missing_origin_login = requests.post(
            f"{base_url}/auth/login",
            json={"username": "eric", "password": "correct-horse-123"},
            timeout=5,
        )
        self.assertEqual(missing_origin_login.status_code, 403)
        self.assertEqual(missing_origin_login.json()["error"]["code"], "CSRF_FAILED")

    def test_frontend_auth_cookie_secure_mode_auto_uses_forwarded_proto(self):
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8")
            + "\n".join(
                [
                    "exports:",
                    "  external_base_url: https://slack.ecochran.dyndns.org",
                    "service:",
                    "  auth:",
                    "    enabled: true",
                    "    allow_registration: true",
                    "    cookie_secure_mode: auto",
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

        insecure = requests.post(
            f"{base_url}/auth/register",
            json={"username": "local-user", "display_name": "Local User", "password": "correct-horse-123"},
            headers={"origin": base_url},
            timeout=5,
        )
        self.assertEqual(insecure.status_code, 201)
        self.assertNotIn("Secure", insecure.headers.get("set-cookie", ""))

        secure = requests.post(
            f"{base_url}/auth/register",
            json={"username": "remote-user", "display_name": "Remote User", "password": "correct-horse-123"},
            headers={"x-forwarded-proto": "https", "origin": base_url.replace("http://", "https://")},
            timeout=5,
        )
        self.assertEqual(secure.status_code, 201)
        self.assertIn("Secure", secure.headers.get("set-cookie", ""))

    def test_frontend_auth_cookie_secure_mode_auto_uses_forwarded_host_mapping(self):
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8")
            + "\n".join(
                [
                    "exports:",
                    "  local_base_url: http://slack.localhost",
                    "  external_base_url: https://slack.ecochran.dyndns.org",
                    "service:",
                    "  auth:",
                    "    enabled: true",
                    "    allow_registration: true",
                    "    cookie_secure_mode: auto",
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

        local_host = requests.post(
            f"{base_url}/auth/register",
            json={"username": "forwarded-local-user", "display_name": "Forwarded Local User", "password": "correct-horse-123"},
            headers={"x-forwarded-host": "slack.localhost", "origin": "http://slack.localhost"},
            timeout=5,
        )
        self.assertEqual(local_host.status_code, 201)
        self.assertNotIn("Secure", local_host.headers.get("set-cookie", ""))

        external_host = requests.post(
            f"{base_url}/auth/register",
            json={"username": "forwarded-external-user", "display_name": "Forwarded External User", "password": "correct-horse-123"},
            headers={"x-forwarded-host": "slack.ecochran.dyndns.org", "origin": "https://slack.ecochran.dyndns.org"},
            timeout=5,
        )
        self.assertEqual(external_host.status_code, 201)
        self.assertIn("Secure", external_host.headers.get("set-cookie", ""))

    def test_frontend_auth_cookie_secure_mode_auto_uses_origin_scheme(self):
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8")
            + "\n".join(
                [
                    "exports:",
                    "  external_base_url: https://slack.ecochran.dyndns.org",
                    "service:",
                    "  auth:",
                    "    enabled: true",
                    "    allow_registration: true",
                    "    cookie_secure_mode: auto",
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

        insecure = requests.post(
            f"{base_url}/auth/register",
            json={"username": "origin-http-user", "display_name": "Origin HTTP User", "password": "correct-horse-123"},
            headers={"origin": base_url},
            timeout=5,
        )
        self.assertEqual(insecure.status_code, 201)
        self.assertNotIn("Secure", insecure.headers.get("set-cookie", ""))

        secure = requests.post(
            f"{base_url}/auth/register",
            json={"username": "origin-https-user", "display_name": "Origin HTTPS User", "password": "correct-horse-123"},
            headers={"origin": "https://slack.ecochran.dyndns.org"},
            timeout=5,
        )
        self.assertEqual(secure.status_code, 201)
        self.assertIn("Secure", secure.headers.get("set-cookie", ""))

    def test_frontend_auth_registration_allowlist_restricts_usernames(self):
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8")
            + "\n".join(
                [
                    "service:",
                    "  auth:",
                    "    enabled: true",
                    "    allow_registration: true",
                    "    registration_allowlist:",
                    "      - ecochran76@gmail.com",
                    "    cookie_secure_mode: never",
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

        allowed = requests.post(
            f"{base_url}/auth/register",
            json={"username": "ecochran76@gmail.com", "display_name": "Eric", "password": "correct-horse-123"},
            headers={"origin": base_url},
            timeout=5,
        )
        self.assertEqual(allowed.status_code, 201)
        self.assertEqual(allowed.json()["session"]["username"], "ecochran76@gmail.com")

        auth_status = requests.get(f"{base_url}/auth/status", timeout=5)
        self.assertEqual(auth_status.status_code, 200)
        self.assertEqual(auth_status.json()["auth"]["registration_mode"], "allowlisted")
        self.assertFalse(auth_status.json()["auth"]["registration_open"])

        register_page = requests.get(f"{base_url}/register", timeout=5)
        self.assertEqual(register_page.status_code, 200)
        self.assertIn("Allowed registration identities", register_page.text)
        self.assertIn("Allowed email or username", register_page.text)
        self.assertIn("ecochran76@gmail.com", register_page.text)

        denied = requests.post(
            f"{base_url}/auth/register",
            json={"username": "mallory@example.com", "display_name": "Mallory", "password": "correct-horse-123"},
            headers={"origin": base_url},
            timeout=5,
        )
        self.assertEqual(denied.status_code, 400)
        self.assertEqual(denied.json()["error"]["code"], "INVALID_REQUEST")
        self.assertIn("restricted", denied.json()["error"]["message"])

    def test_frontend_auth_login_rate_limit_enforced(self):
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8")
            + "\n".join(
                [
                    "service:",
                    "  auth:",
                    "    enabled: true",
                    "    allow_registration: true",
                    "    cookie_secure_mode: never",
                    "    login_attempt_window_seconds: 3600",
                    "    login_attempt_max_failures: 2",
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

        registered = requests.post(
            f"{base_url}/auth/register",
            json={"username": "eric", "display_name": "Eric", "password": "correct-horse-123"},
            headers={"origin": base_url},
            timeout=5,
        )
        self.assertEqual(registered.status_code, 201)

        first_bad = requests.post(
            f"{base_url}/auth/login",
            json={"username": "eric", "password": "wrong-horse-123"},
            headers={"origin": base_url},
            timeout=5,
        )
        self.assertEqual(first_bad.status_code, 400)
        self.assertEqual(first_bad.json()["error"]["code"], "INVALID_REQUEST")

        second_bad = requests.post(
            f"{base_url}/auth/login",
            json={"username": "eric", "password": "wrong-horse-123"},
            headers={"origin": base_url},
            timeout=5,
        )
        self.assertEqual(second_bad.status_code, 429)
        self.assertEqual(second_bad.json()["error"]["code"], "RATE_LIMITED")
        self.assertGreaterEqual(second_bad.json()["error"]["details"]["retry_after_seconds"], 1)
        self.assertEqual(second_bad.json()["error"]["details"]["attempt_limit"], 2)
        self.assertEqual(second_bad.json()["error"]["details"]["window_seconds"], 3600)

        blocked_good = requests.post(
            f"{base_url}/auth/login",
            json={"username": "eric", "password": "correct-horse-123"},
            headers={"origin": base_url},
            timeout=5,
        )
        self.assertEqual(blocked_good.status_code, 429)
        self.assertEqual(blocked_good.json()["error"]["code"], "RATE_LIMITED")

        auth_status = requests.get(f"{base_url}/auth/status", timeout=5)
        self.assertEqual(auth_status.status_code, 200)
        self.assertEqual(auth_status.json()["auth"]["login_attempt_window_seconds"], 3600)
        self.assertEqual(auth_status.json()["auth"]["login_attempt_max_failures"], 2)

    def test_frontend_auth_session_idle_timeout_enforced(self):
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8")
            + "\n".join(
                [
                    "service:",
                    "  auth:",
                    "    enabled: true",
                    "    allow_registration: true",
                    "    cookie_secure_mode: never",
                    "    session_idle_timeout_seconds: 300",
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

        stale_session = requests.Session()
        registered = stale_session.post(
            f"{base_url}/auth/register",
            json={"username": "idle-user", "display_name": "Idle User", "password": "correct-horse-123"},
            headers={"origin": base_url},
            timeout=5,
        )
        self.assertEqual(registered.status_code, 201)
        session_id = registered.json()["session"]["session_id"]

        viewer_session = requests.Session()
        logged_in = viewer_session.post(
            f"{base_url}/auth/login",
            json={"username": "idle-user", "password": "correct-horse-123"},
            headers={"origin": base_url},
            timeout=5,
        )
        self.assertEqual(logged_in.status_code, 200)

        service = get_app_service(str(self.config_path))
        conn = service.connect()
        stale_seen = (datetime.now(UTC) - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S+00:00")
        conn.execute("UPDATE auth_sessions SET last_seen_at = ? WHERE id = ?", (stale_seen, session_id))
        conn.commit()

        auth_status = viewer_session.get(f"{base_url}/auth/status", timeout=5)
        self.assertEqual(auth_status.status_code, 200)
        self.assertEqual(auth_status.json()["auth"]["session_idle_timeout_seconds"], 300)

        sessions_listing = viewer_session.get(f"{base_url}/auth/sessions", timeout=5)
        self.assertEqual(sessions_listing.status_code, 200)
        listed = next(item for item in sessions_listing.json()["sessions"] if item["session_id"] == session_id)
        self.assertTrue(listed["idle_expired"])
        self.assertFalse(listed["active"])

        auth_session = stale_session.get(f"{base_url}/auth/session", timeout=5)
        self.assertEqual(auth_session.status_code, 200)
        self.assertFalse(auth_session.json()["session"]["authenticated"])

    def test_export_file_serving_endpoint(self):
        exports_root = self.root / "exports-root"
        bundle_dir = exports_root / "channel-day-default-general-2026-04-12-abc123"
        attachment_dir = bundle_dir / "attachments" / "incident"
        attachment_dir.mkdir(parents=True)
        (bundle_dir / "index.html").write_text("<html><body><h1>preview smoke</h1></body></html>", encoding="utf-8")
        (attachment_dir / "report.pdf").write_bytes(b"%PDF-1.4\n")
        (attachment_dir / "preview.txt").write_text("preview body\n", encoding="utf-8")
        (attachment_dir / "email-preview.html").write_text("<div>Email preview body</div>", encoding="utf-8")
        (attachment_dir / "archive.bin").write_bytes(b"\x00\x01")
        docx_input = bundle_dir / "channel-day.json"
        docx_path = attachment_dir / "sample.docx"
        pptx_path = attachment_dir / "slides.pptx"
        xlsx_path = attachment_dir / "sheet.xlsx"
        odt_path = attachment_dir / "brief.odt"
        odp_path = attachment_dir / "slides.odp"
        ods_path = attachment_dir / "sheet.ods"
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
        import zipfile
        with zipfile.ZipFile(pptx_path, "w") as zf:
            zf.writestr(
                "ppt/slides/slide1.xml",
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Launch roadmap</a:t></a:r><a:br/><a:r><a:t>Q4 milestone</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>',
            )
        with zipfile.ZipFile(xlsx_path, "w") as zf:
            zf.writestr(
                "xl/sharedStrings.xml",
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Revenue plan</t></si></sst>',
            )
            zf.writestr(
                "xl/worksheets/sheet1.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="s"><v>0</v></c><c t="inlineStr"><is><t>Projected pipeline</t></is></c><c><v>42</v></c></row></sheetData></worksheet>',
            )
        with zipfile.ZipFile(odt_path, "w") as zf:
            zf.writestr(
                "content.xml",
                '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text><text:p>OpenDocument board brief</text:p></office:text></office:body></office:document-content>',
            )
        with zipfile.ZipFile(odp_path, "w") as zf:
            zf.writestr(
                "content.xml",
                '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:presentation><draw:page draw:name="Launch"><text:p>OpenDocument launch deck</text:p></draw:page></office:presentation></office:body></office:document-content>',
            )
        with zipfile.ZipFile(ods_path, "w") as zf:
            zf.writestr(
                "content.xml",
                '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:spreadsheet><table:table table:name="Sheet A"><table:table-row><table:table-cell><text:p>OpenDocument revenue sheet</text:p></table:table-cell><table:table-cell><text:p>84</text:p></table:table-cell></table:table-row></table:table></office:spreadsheet></office:body></office:document-content>',
            )

        config_text = self.config_path.read_text(encoding="utf-8")
        self.config_path.write_text(
            config_text
            + "\n".join(
                [
                    "exports:",
                    f"  root_dir: {exports_root}",
                    "  local_base_url: http://slack.localhost",
                    "  external_base_url: https://slack.ecochran.dyndns.org",
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

        bundle_report = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123",
            timeout=5,
        )
        self.assertEqual(bundle_report.status_code, 200)
        self.assertIn("text/html", bundle_report.headers["content-type"])
        self.assertIn("<h1>preview smoke</h1>", bundle_report.text)

        bundle_report_slash = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123/",
            timeout=5,
        )
        self.assertEqual(bundle_report_slash.status_code, 200)
        self.assertIn("text/html", bundle_report_slash.headers["content-type"])
        self.assertIn("<h1>preview smoke</h1>", bundle_report_slash.text)

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

        html_preview = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/email-preview.html/preview",
            timeout=5,
        )
        self.assertEqual(html_preview.status_code, 200)
        self.assertIn("iframe", html_preview.text)
        self.assertIn("Email preview body", html_preview.text)
        self.assertIn("<article", docx_preview.text)

        pptx_preview = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/slides.pptx/preview",
            timeout=5,
        )
        self.assertEqual(pptx_preview.status_code, 200)
        self.assertIn("PowerPoint preview", pptx_preview.text)
        self.assertIn("Launch roadmap", pptx_preview.text)
        self.assertIn("Slide 1", pptx_preview.text)

        xlsx_preview = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/sheet.xlsx/preview",
            timeout=5,
        )
        self.assertEqual(xlsx_preview.status_code, 200)
        self.assertIn("Spreadsheet preview", xlsx_preview.text)
        self.assertIn("Revenue plan", xlsx_preview.text)
        self.assertIn("Projected pipeline", xlsx_preview.text)

        odt_preview = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/brief.odt/preview",
            timeout=5,
        )
        self.assertEqual(odt_preview.status_code, 200)
        self.assertIn("OpenDocument text preview", odt_preview.text)
        self.assertIn("OpenDocument board brief", odt_preview.text)

        odp_preview = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/slides.odp/preview",
            timeout=5,
        )
        self.assertEqual(odp_preview.status_code, 200)
        self.assertIn("OpenDocument presentation preview", odp_preview.text)
        self.assertIn("OpenDocument launch deck", odp_preview.text)
        self.assertIn("Launch", odp_preview.text)

        ods_preview = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/sheet.ods/preview",
            timeout=5,
        )
        self.assertEqual(ods_preview.status_code, 200)
        self.assertIn("OpenDocument spreadsheet preview", ods_preview.text)
        self.assertIn("OpenDocument revenue sheet", ods_preview.text)
        self.assertIn("84", ods_preview.text)

        unsupported = requests.get(
            f"{base_url}/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/archive.bin/preview",
            timeout=5,
        )
        self.assertEqual(unsupported.status_code, 415)
        self.assertEqual(unsupported.json()["error"]["code"], "PREVIEW_UNSUPPORTED")

        exports = requests.get(f"{base_url}/v1/exports", timeout=5)
        self.assertEqual(exports.status_code, 200)
        self.assertTrue(exports.json()["ok"])
        self.assertEqual(len(exports.json()["exports"]), 1)
        self.assertEqual(exports.json()["exports"][0]["export_id"], bundle_dir.name)
        self.assertEqual(
            exports.json()["exports"][0]["bundle_url"],
            f"http://slack.localhost/exports/{bundle_dir.name}",
        )

        exports_index = requests.get(f"{base_url}/exports", timeout=5)
        self.assertEqual(exports_index.status_code, 200)
        self.assertIn("Slack Mirror Exports", exports_index.text)
        self.assertIn("Create channel-day export", exports_index.text)
        self.assertIn("create-export-button", exports_index.text)
        self.assertIn(bundle_dir.name, exports_index.text)
        self.assertIn(f"data-export-rename-toggle='{bundle_dir.name}'", exports_index.text)
        self.assertIn(f"export-rename-row-{bundle_dir.name}", exports_index.text)
        self.assertIn(f"export-rename-input-{bundle_dir.name}", exports_index.text)
        self.assertIn(f"data-export-rename-save='{bundle_dir.name}'", exports_index.text)
        self.assertIn(f"data-export-rename-cancel='{bundle_dir.name}'", exports_index.text)
        self.assertIn(f"data-export-delete='{bundle_dir.name}'", exports_index.text)
        self.assertNotIn("window.prompt('Rename export bundle'", exports_index.text)
        self.assertIn(f"id='export-row-{bundle_dir.name}'", exports_index.text)
        self.assertIn("insertCreatedExport(", exports_index.text)
        self.assertIn("exportRowHtml(", exports_index.text)
        self.assertIn("bindInlineManagerActions(", exports_index.text)
        self.assertIn("setInlineManagerBusyState(", exports_index.text)
        self.assertIn("button.dataset.busy==='true'", exports_index.text)
        self.assertIn("Created export", exports_index.text)
        self.assertIn("itemLabel:'export'", exports_index.text)
        self.assertNotIn(
            "if(resp.ok){window.location.reload();return;}const data=await resp.json().catch(()=>({error:{message:'Create failed'}}));",
            exports_index.text,
        )
        self.assertIn("applyExportRename(", exports_index.text)
        self.assertIn("removeExportRow(", exports_index.text)
        self.assertIn("export-empty-row", exports_index.text)
        self.assertIn("ensureExportEmptyStateRow(", exports_index.text)
        self.assertNotIn(
            "if(resp.ok){window.location.reload();return;}const data=await resp.json().catch(()=>({error:{message:'Rename failed'}}));",
            exports_index.text,
        )
        self.assertNotIn(
            "if(resp.ok){window.location.reload();return;}const data=await resp.json().catch(()=>({error:{message:'Delete failed'}}));",
            exports_index.text,
        )

        external_manifest = requests.get(
            f"{base_url}/v1/exports/{bundle_dir.name}",
            params={"audience": "external"},
            timeout=5,
        )
        self.assertEqual(external_manifest.status_code, 200)
        manifest = external_manifest.json()["export"]
        self.assertEqual(
            manifest["bundle_url"],
            f"https://slack.ecochran.dyndns.org/exports/{bundle_dir.name}",
        )
        file_map = {entry["relpath"]: entry for entry in manifest["files"]}
        self.assertEqual(
            file_map["attachments/incident/report.pdf"]["preview_url"],
            f"https://slack.ecochran.dyndns.org/exports/{bundle_dir.name}/attachments/incident/report.pdf/preview",
        )
        self.assertEqual(
            file_map["attachments/incident/slides.pptx"]["preview_url"],
            f"https://slack.ecochran.dyndns.org/exports/{bundle_dir.name}/attachments/incident/slides.pptx/preview",
        )
        self.assertEqual(
            file_map["attachments/incident/sheet.xlsx"]["preview_url"],
            f"https://slack.ecochran.dyndns.org/exports/{bundle_dir.name}/attachments/incident/sheet.xlsx/preview",
        )
        self.assertEqual(
            file_map["attachments/incident/brief.odt"]["preview_url"],
            f"https://slack.ecochran.dyndns.org/exports/{bundle_dir.name}/attachments/incident/brief.odt/preview",
        )
        self.assertEqual(
            file_map["attachments/incident/slides.odp"]["preview_url"],
            f"https://slack.ecochran.dyndns.org/exports/{bundle_dir.name}/attachments/incident/slides.odp/preview",
        )
        self.assertEqual(
            file_map["attachments/incident/sheet.ods"]["preview_url"],
            f"https://slack.ecochran.dyndns.org/exports/{bundle_dir.name}/attachments/incident/sheet.ods/preview",
        )
        self.assertIsNone(file_map["attachments/incident/archive.bin"]["preview_url"])

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
