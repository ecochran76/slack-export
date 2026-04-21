import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from slack_mirror.core.db import (
    connect,
    enqueue_derived_text_job,
    get_derived_text,
    get_derived_text_chunks,
    get_message_embedding,
    get_workspace_by_name,
    mark_derived_text_job_status,
    upsert_channel,
    upsert_derived_text,
    upsert_derived_text_chunk_embedding,
    upsert_message,
    upsert_message_embedding,
    upsert_user,
    upsert_workspace,
)
from slack_mirror.service.app import SlackMirrorAppService
from slack_mirror.sync.derived_text import backfill_derived_text_chunk_embeddings
from slack_mirror.sync.embeddings import process_embedding_jobs


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
                    "exports:",
                    "  local_base_url: http://slack.localhost",
                    "  external_base_url: https://slack.example.test",
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

    def test_validate_live_runtime_includes_reconcile_fields(self):
        report = SimpleNamespace(
            ok=True,
            status="pass",
            summary="Summary: PASS",
            exit_code=0,
            failure_count=0,
            warning_count=0,
            failure_codes=[],
            warning_codes=[],
            failures=[],
            warnings=[],
            workspaces=[
                SimpleNamespace(
                    name="default",
                    event_errors=0,
                    embedding_errors=0,
                    event_pending=0,
                    embedding_pending=0,
                    stale_channels=5,
                    stale_warning_suppressed=True,
                    active_recent_channels=2,
                    shell_like_zero_message_channels=1,
                    unexpected_empty_channels=0,
                    reconcile_state_present=True,
                    reconcile_state_age_seconds=12.0,
                    reconcile_auth_mode="user",
                    reconcile_iso_utc="2026-04-13T02:00:00+00:00",
                    reconcile_attempted=2,
                    reconcile_downloaded=2,
                    reconcile_warnings=0,
                    reconcile_failed=0,
                    failure_codes=[],
                    warning_codes=[],
                )
            ],
        )
        with patch("slack_mirror.service.app._build_live_validation_report", return_value=report):
            result = self.service.validate_live_runtime(require_live_units=True)
        self.assertTrue(result.ok)
        self.assertEqual(result.workspaces[0]["name"], "default")
        self.assertTrue(result.workspaces[0]["reconcile_state_present"])
        self.assertEqual(result.workspaces[0]["reconcile_downloaded"], 2)
        self.assertEqual(result.workspaces[0]["reconcile_failed"], 0)

    def test_create_channel_day_export_invokes_script_and_returns_manifest(self):
        export_root = self.root / "exports"
        bundle_dir = export_root / "channel-day-default-general-2026-04-12-abc123"
        bundle_dir.mkdir(parents=True)
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8")
            + "\n".join(
                [
                    "exports:",
                    f"  root_dir: {export_root}",
                    "  local_base_url: http://slack.localhost",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        service = SlackMirrorAppService(str(self.config_path))
        with patch("slack_mirror.service.app.subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(
                returncode=0,
                stdout=f"Export bundle: {bundle_dir}\n",
                stderr="",
            )
            payload = service.create_channel_day_export(
                workspace="default",
                channel="general",
                day="2026-04-12",
            )
        self.assertEqual(payload["export_id"], bundle_dir.name)
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["producer"]["name"], "slack-mirror")
        self.assertEqual(payload["provenance"]["url_contract_source"], "current_service_config")
        self.assertEqual(payload["bundle_url"], f"http://slack.localhost/exports/{bundle_dir.name}")
        invoked = mock_run.call_args.args[0]
        self.assertIn("--managed-export", invoked)
        self.assertIn("--workspace", invoked)
        self.assertIn("default", invoked)
        self.assertIn("--channel", invoked)
        self.assertIn("general", invoked)

    def test_list_workspace_channels_returns_valid_choices(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C123", "name": "general", "is_private": False})
        upsert_channel(self.conn, workspace_id, {"id": "D123", "user": "U123", "is_im": True})
        upsert_message(
            self.conn,
            workspace_id,
            "C123",
            {
                "ts": "1712870400.000100",
                "user": "U1",
                "text": "hello",
                "channel": "C123",
            },
        )
        rows = self.service.list_workspace_channels(self.conn, workspace="default")
        self.assertEqual(rows[0]["name"], "general")
        self.assertEqual(rows[0]["channel_class"], "public")
        self.assertEqual(rows[0]["message_count"], 1)
        self.assertEqual(rows[0]["latest_message_day"], "2024-04-11")
        self.assertEqual(rows[1]["channel_class"], "im")

    def test_list_runtime_reports_includes_base_url_choices(self):
        payload = self.service.list_runtime_reports()
        self.assertEqual(
            payload.base_url_choices,
            [
                {"audience": "local", "base_url": "http://slack.localhost"},
                {"audience": "external", "base_url": "https://slack.example.test"},
            ],
        )

    def test_create_runtime_report_uses_shared_runtime_payloads(self):
        runtime_status = SimpleNamespace(
            ok=True,
            api_wrapper_present=True,
            cli_wrapper_present=True,
            mcp_wrapper_present=True,
            api_service_present=True,
            config_present=True,
            db_present=True,
            cache_present=True,
            rollback_snapshot_present=False,
            services={"slack-mirror-api.service": "active"},
            reconcile_workspaces=[],
        )
        live_validation = SimpleNamespace(
            ok=True,
            status="pass",
            summary="Summary: PASS",
            lines=[],
            exit_code=0,
            failure_count=0,
            warning_count=0,
            failure_codes=[],
            warning_codes=[],
            workspaces=[],
        )
        with patch.object(self.service, "runtime_status", return_value=runtime_status), patch.object(
            self.service,
            "validate_live_runtime",
            return_value=live_validation,
        ), patch("slack_mirror.service.app.write_runtime_report_snapshot") as mock_write:
            mock_write.return_value = {"name": "ops-report"}
            payload = self.service.create_runtime_report(base_url="http://slack.localhost", name="ops report", timeout=7.5)
        self.assertEqual(payload["name"], "ops-report")
        kwargs = mock_write.call_args.kwargs
        self.assertEqual(str(kwargs["config_path"]), str(self.config_path))
        self.assertEqual(kwargs["base_url"], "http://slack.localhost")
        self.assertEqual(kwargs["name"], "ops report")
        self.assertEqual(kwargs["timeout"], 7.5)
        self.assertEqual(kwargs["runtime_status"]["ok"], True)
        self.assertEqual(kwargs["runtime_status"]["status"]["services"]["slack-mirror-api.service"], "active")
        self.assertEqual(kwargs["live_validation"]["ok"], True)
        self.assertEqual(kwargs["live_validation"]["validation"]["status"], "pass")

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

    def test_search_readiness_reports_provider_and_issue_details(self):
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
            metadata={"provider": "local_host_tools", "origin": "test"},
        )

        enqueue_derived_text_job(
            self.conn,
            workspace_id=workspace_id,
            source_kind="file",
            source_id="F2",
            derivation_kind="attachment_text",
            reason="sync",
        )
        enqueue_derived_text_job(
            self.conn,
            workspace_id=workspace_id,
            source_kind="file",
            source_id="F3",
            derivation_kind="ocr_text",
            reason="sync",
        )
        enqueue_derived_text_job(
            self.conn,
            workspace_id=workspace_id,
            source_kind="file",
            source_id="F4",
            derivation_kind="ocr_text",
            reason="sync",
        )
        error_job = self.conn.execute(
            "SELECT id FROM derived_text_jobs WHERE workspace_id = ? AND source_id = 'F3' AND derivation_kind = 'ocr_text'",
            (workspace_id,),
        ).fetchone()["id"]
        skipped_job = self.conn.execute(
            "SELECT id FROM derived_text_jobs WHERE workspace_id = ? AND source_id = 'F4' AND derivation_kind = 'ocr_text'",
            (workspace_id,),
        ).fetchone()["id"]
        mark_derived_text_job_status(self.conn, job_id=int(error_job), status="error", error="ocr_tools_unavailable")
        mark_derived_text_job_status(self.conn, job_id=int(skipped_job), status="skipped", error="pdf_has_text_layer")

        readiness = self.service.search_readiness(self.conn, workspace="default")

        self.assertEqual(readiness["status"], "degraded")
        self.assertEqual(readiness["derived_text"]["attachment_text"]["jobs"]["pending"], 1)
        self.assertEqual(readiness["derived_text"]["attachment_text"]["providers"], {})
        self.assertEqual(readiness["derived_text"]["ocr_text"]["providers"]["local_host_tools"], 1)
        self.assertEqual(readiness["derived_text"]["ocr_text"]["jobs"]["error"], 1)
        self.assertEqual(readiness["derived_text"]["ocr_text"]["jobs"]["skipped"], 1)
        self.assertEqual(readiness["derived_text"]["ocr_text"]["issue_reasons"]["ocr_tools_unavailable"], 1)
        self.assertEqual(readiness["derived_text"]["ocr_text"]["issue_reasons"]["pdf_has_text_layer"], 1)

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
        process_embedding_jobs(self.conn, workspace_id=workspace_id, limit=20)
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
        self.assertEqual(health["benchmark"]["dataset_path"], str(dataset))
        self.assertIn("query_reports", health["benchmark"])
        self.assertEqual(health["benchmark_thresholds"]["min_hit_at_10"], 0.8)

    def test_search_health_reports_derived_text_benchmark(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C123", "name": "general"})
        upsert_message(
            self.conn,
            workspace_id,
            "C123",
            {"ts": "1700000000.000100", "user": "U1", "text": "baseline message for readiness", "channel": "C123"},
        )
        process_embedding_jobs(self.conn, workspace_id=workspace_id, limit=20)
        self.conn.execute(
            """
            INSERT INTO files(workspace_id, file_id, name, title, mimetype, local_path, raw_json)
            VALUES (?, 'F9', 'notes.txt', 'Playbook', 'text/plain', '/tmp/playbook.txt', '{}')
            """,
            (workspace_id,),
        )
        upsert_derived_text(
            self.conn,
            workspace_id=workspace_id,
            source_kind="file",
            source_id="F9",
            derivation_kind="attachment_text",
            extractor="utf8_text",
            text="The catastrophic rollback signature appears in the late appendix section.",
            media_type="text/plain",
            local_path="/tmp/playbook.txt",
            metadata={"origin": "test"},
        )
        backfill_derived_text_chunk_embeddings(
            self.conn,
            workspace_id=workspace_id,
            model_id="local-hash-128",
            limit=100,
            derivation_kind="attachment_text",
            provider=self.service.message_embedding_provider(),
        )
        dataset = self.root / "derived_eval.jsonl"
        dataset.write_text(
            '{"query":"catastrophic rollback signature","derivation_kind":"attachment_text","relevant":{"file:F9:attachment_text:utf8_text":2,"Playbook":1}}\n',
            encoding="utf-8",
        )

        health = self.service.search_health(
            self.conn,
            workspace="default",
            dataset_path=str(dataset),
            benchmark_target="derived_text",
            mode="semantic",
            limit=10,
            model_id="local-hash-128",
        )

        self.assertEqual(health["status"], "pass")
        self.assertEqual(health["benchmark_target"], "derived_text")
        self.assertEqual(health["benchmark"]["corpus"], "slack-derived-text")
        self.assertGreaterEqual(health["benchmark"]["hit_at_3"], 1.0)
        first_query = health["benchmark"]["query_reports"][0]
        self.assertEqual(first_query["derivation_kind"], "attachment_text")
        self.assertTrue(first_query["top_result_details"])
        self.assertEqual(first_query["top_result_details"][0]["source_id"], "F9")
        self.assertIsNotNone(first_query["top_result_details"][0]["chunk_index"])

    def test_semantic_rollout_plan_reports_profile_coverage_and_commands(self):
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
            VALUES (?, 'F10', 'notes.txt', 'Notes', 'text/plain', '/tmp/notes.txt', '{}')
            """,
            (workspace_id,),
        )
        upsert_derived_text(
            self.conn,
            workspace_id=workspace_id,
            source_kind="file",
            source_id="F10",
            derivation_kind="attachment_text",
            extractor="utf8_text",
            text="incident review attachment text",
            media_type="text/plain",
            local_path="/tmp/notes.txt",
            metadata={"origin": "test"},
        )

        plan = self.service.semantic_rollout_plan(
            self.conn,
            workspace="default",
            profile_name="local-bge",
            limit=25,
            channels=["C123"],
            derived_kind="attachment_text",
            derived_source_kind="file",
        )

        self.assertEqual(plan["profile"]["name"], "local-bge")
        self.assertEqual(plan["profile"]["model"], "BAAI/bge-m3")
        self.assertEqual(plan["coverage"]["messages"]["total"], 1)
        self.assertEqual(plan["coverage"]["messages"]["missing"], 1)
        self.assertGreaterEqual(plan["coverage"]["derived_text_chunks"]["total"], 1)
        self.assertEqual(plan["status"], "rollout_needed")
        self.assertIn("provider-probe", plan["commands"]["provider_probe"])
        self.assertIn("embeddings-backfill", plan["commands"]["message_embeddings_backfill"])
        self.assertIn("--retrieval-profile", plan["commands"]["message_embeddings_backfill"])
        self.assertIn("--retrieval-profile", plan["commands"]["derived_text_embeddings_backfill"])
        self.assertIn("--retrieval-profile", plan["commands"]["search_health"])

    def test_semantic_readiness_reports_profile_states(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C123", "name": "general"})
        upsert_message(
            self.conn,
            workspace_id,
            "C123",
            {"ts": "1700000000.000100", "user": "U1", "text": "incident review follow-up", "channel": "C123"},
        )
        process_embedding_jobs(self.conn, workspace_id=workspace_id, model_id="local-hash-128", limit=20)
        self.service.config.data.setdefault("search", {})["retrieval_profiles"] = {
            "local-wide": {
                "mode": "hybrid",
                "model": "local-hash-256",
                "semantic_provider": {"type": "local_hash"},
                "rerank": False,
            }
        }

        readiness = self.service.semantic_readiness(
            self.conn,
            workspace="default",
            profile_names=["baseline", "local-wide"],
            include_commands=True,
            command_limit=10,
        )

        self.assertEqual(readiness["scope"], "workspace")
        workspace = readiness["workspaces"][0]
        profile_map = {profile["name"]: profile for profile in workspace["profiles"]}
        self.assertEqual(profile_map["baseline"]["state"], "ready")
        self.assertEqual(profile_map["local-wide"]["state"], "rollout_needed")
        self.assertIn("message_embeddings_backfill", profile_map["local-wide"]["commands"])

    def test_search_scale_review_reports_counts_latency_and_decision(self):
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
            VALUES (?, 'F11', 'incident.txt', 'Incident Notes', 'text/plain', '/tmp/incident.txt', '{}')
            """,
            (workspace_id,),
        )
        upsert_derived_text(
            self.conn,
            workspace_id=workspace_id,
            source_kind="file",
            source_id="F11",
            derivation_kind="attachment_text",
            extractor="utf8_text",
            text="incident review attachment notes",
            media_type="text/plain",
            local_path="/tmp/incident.txt",
            metadata={"origin": "test"},
        )
        process_embedding_jobs(self.conn, workspace_id=workspace_id, model_id="local-hash-128", limit=20)
        backfill_derived_text_chunk_embeddings(
            self.conn,
            workspace_id=workspace_id,
            model_id="local-hash-128",
            limit=100,
            provider=self.service.message_embedding_provider(),
        )

        review = self.service.search_scale_review(
            self.conn,
            workspace="default",
            queries=["incident review"],
            profile_names=["baseline"],
            repeats=2,
            limit=5,
        )

        self.assertEqual(review["workspace"], "default")
        self.assertEqual(review["corpus"]["messages"]["count"], 1)
        self.assertEqual(review["corpus"]["messages"]["embeddings_by_model"]["local-hash-128"], 1)
        self.assertEqual(review["corpus"]["derived_text"]["counts"]["attachment_text"], 1)
        self.assertGreaterEqual(review["corpus"]["derived_text"]["chunk_counts"]["attachment_text"], 1)
        self.assertEqual(len(review["runs"]), 1)
        self.assertEqual(review["runs"][0]["profile"], "baseline")
        self.assertEqual(review["runs"][0]["repeats"], 2)
        self.assertEqual(len(review["runs"][0]["result_counts"]), 2)
        self.assertIn("p95", review["runs"][0]["latency_ms"])
        self.assertEqual(review["decision"]["index_backend"], "sqlite_exact")
        self.assertEqual(review["decision"]["inference_boundary"], "in_process_for_baseline")

    def test_benchmark_dataset_report_resolves_labels_and_model_coverage(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C1", "name": "general"})
        upsert_user(self.conn, workspace_id, {"id": "U1", "name": "alice", "real_name": "Alice Example"})
        upsert_message(self.conn, workspace_id, "C1", {"ts": "1.0", "text": "alpha benchmark target", "user": "U1"})
        upsert_message_embedding(
            self.conn,
            workspace_id=workspace_id,
            channel_id="C1",
            ts="1.0",
            model_id="local-hash-128",
            embedding=[0.1, 0.2],
            content_hash="h1",
        )
        upsert_derived_text(
            self.conn,
            workspace_id=workspace_id,
            source_kind="file",
            source_id="F1",
            derivation_kind="attachment_text",
            extractor="utf8_text",
            text="derived benchmark target",
        )
        derived = get_derived_text(
            self.conn,
            workspace_id=workspace_id,
            source_kind="file",
            source_id="F1",
            derivation_kind="attachment_text",
            extractor="utf8_text",
        )
        chunks = get_derived_text_chunks(self.conn, derived_text_id=int(derived["id"]))
        upsert_derived_text_chunk_embedding(
            self.conn,
            derived_text_chunk_id=int(chunks[0]["id"]),
            workspace_id=workspace_id,
            model_id="local-hash-128",
            embedding=[0.3, 0.4],
            content_hash="h2",
        )
        dataset = self.root / "bench.jsonl"
        dataset.write_text(
            "\n".join(
                [
                    '{"id":"q1","query":"alpha","intent":"message_exact","relevant":{"general:1.0":2}}',
                    '{"id":"q2","query":"derived","intent":"derived_exact","relevant":{"file:F1:attachment_text:utf8_text":2}}',
                ]
            ),
            encoding="utf-8",
        )

        result = self.service.benchmark_dataset_report(
            self.conn,
            workspace="default",
            dataset_path=str(dataset),
            profile_names=["baseline", "local-bge-http"],
        )

        self.assertEqual(result["status"], "pass_with_warnings")
        self.assertEqual(result["queries"], 2)
        self.assertEqual(result["labels"], 2)
        self.assertEqual(result["resolved_labels"], 2)
        self.assertEqual(result["unresolved_labels"], [])
        baseline = result["profiles"][0]
        bge = result["profiles"][1]
        self.assertEqual(baseline["coverage"]["covered"], 2)
        self.assertEqual(baseline["coverage"]["coverage_ratio"], 1.0)
        self.assertEqual(bge["coverage"]["covered"], 0)
        self.assertEqual(bge["coverage"]["coverage_ratio"], 0.0)

    def test_backfill_benchmark_dataset_embeddings_only_targets_labels(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C1", "name": "general"})
        upsert_user(self.conn, workspace_id, {"id": "U1", "name": "alice", "real_name": "Alice Example"})
        upsert_message(self.conn, workspace_id, "C1", {"ts": "1.0", "text": "alpha benchmark target", "user": "U1"})
        upsert_message(self.conn, workspace_id, "C1", {"ts": "2.0", "text": "not in benchmark", "user": "U1"})
        dataset = self.root / "bench-targets.jsonl"
        dataset.write_text(
            '{"id":"q1","query":"alpha","intent":"message_exact","relevant":{"general:1.0":2}}\n',
            encoding="utf-8",
        )

        result = self.service.backfill_benchmark_dataset_embeddings(
            self.conn,
            workspace="default",
            dataset_path=str(dataset),
            retrieval_profile_name="baseline",
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["message_targets"], 1)
        self.assertEqual(result["messages"]["embedded"], 1)
        self.assertIsNotNone(
            get_message_embedding(
                self.conn,
                workspace_id=workspace_id,
                channel_id="C1",
                ts="1.0",
                model_id="local-hash-128",
            )
        )
        self.assertIsNone(
            get_message_embedding(
                self.conn,
                workspace_id=workspace_id,
                channel_id="C1",
                ts="2.0",
                model_id="local-hash-128",
            )
        )

    def test_benchmark_profile_diagnostics_reports_rank_movement_without_text(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C1", "name": "general"})
        upsert_user(self.conn, workspace_id, {"id": "U1", "name": "alice", "real_name": "Alice Example"})
        upsert_message(self.conn, workspace_id, "C1", {"ts": "1.0", "text": "alpha benchmark target", "user": "U1"})
        upsert_message(self.conn, workspace_id, "C1", {"ts": "2.0", "text": "other message", "user": "U1"})
        process_embedding_jobs(self.conn, workspace_id=workspace_id, model_id="local-hash-128", limit=10)
        dataset = self.root / "bench-diagnose.jsonl"
        dataset.write_text(
            '{"id":"q1","query":"alpha","intent":"message_exact","relevant":{"general:1.0":2}}\n',
            encoding="utf-8",
        )

        result = self.service.benchmark_profile_diagnostics(
            self.conn,
            workspace="default",
            dataset_path=str(dataset),
            profile_names=["baseline"],
            limit=5,
            fusion_method="rrf",
        )

        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["include_text"])
        self.assertEqual(result["fusion_method"], "rrf")
        query = result["query_reports"][0]
        run = query["profiles"][0]
        target = run["expected_targets"][0]
        self.assertEqual(run["profile"], "baseline")
        self.assertEqual(target["rank"], 1)
        self.assertEqual(target["movement_vs_baseline"], "unchanged")
        self.assertEqual(target["matched_result"]["labels"], ["C1:1.0", "general:1.0"])
        self.assertIn("explain", target["matched_result"])
        self.assertNotIn("text", target["matched_result"])
        self.assertNotIn("snippet_text", target["matched_result"])

    def test_benchmark_query_variants_compares_normalized_forms_without_content(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C1", "name": "general"})
        upsert_user(self.conn, workspace_id, {"id": "U1", "name": "alice", "real_name": "Alice Example"})
        upsert_message(self.conn, workspace_id, "C1", {"ts": "1.0", "text": "Nylon 5 9 target", "user": "U1"})
        dataset = self.root / "bench-variants.jsonl"
        dataset.write_text(
            '{"id":"q1","query":"Nylon-5,9","intent":"punctuation_normalization","relevant":{"general:1.0":2}}\n',
            encoding="utf-8",
        )

        result = self.service.benchmark_query_variants(
            self.conn,
            workspace="default",
            dataset_path=str(dataset),
            profile_names=["baseline"],
            variant_names=["original", "alnum"],
            mode="lexical",
            limit=5,
            include_details=True,
        )

        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["include_details"])
        runs = {run["variant"]: run for run in result["runs"]}
        self.assertEqual(runs["original"]["metrics"]["hit_at_10"], 0.0)
        self.assertEqual(runs["alnum"]["metrics"]["hit_at_10"], 1.0)
        self.assertEqual(result["best_run"]["variant"], "alnum")
        self.assertIn("general:1.0", runs["alnum"]["query_reports"][0]["top_results"])
        self.assertNotIn("text", str(result))
        self.assertNotIn("snippet_text", str(result))

    def test_search_health_rejects_hybrid_for_derived_text_target(self):
        with self.assertRaisesRegex(ValueError, "derived_text benchmark target only supports lexical or semantic mode"):
            self.service.search_health(
                self.conn,
                workspace="default",
                dataset_path=str(self.root / "unused.jsonl"),
                benchmark_target="derived_text",
                mode="hybrid",
            )

    def test_search_health_applies_extraction_threshold_policy(self):
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
            metadata={"provider": "local_host_tools", "origin": "test"},
        )

        enqueue_derived_text_job(
            self.conn,
            workspace_id=workspace_id,
            source_kind="file",
            source_id="F2",
            derivation_kind="attachment_text",
            reason="sync",
        )
        enqueue_derived_text_job(
            self.conn,
            workspace_id=workspace_id,
            source_kind="file",
            source_id="F3",
            derivation_kind="ocr_text",
            reason="sync",
        )
        error_job = self.conn.execute(
            "SELECT id FROM derived_text_jobs WHERE workspace_id = ? AND source_id = 'F3' AND derivation_kind = 'ocr_text'",
            (workspace_id,),
        ).fetchone()["id"]
        mark_derived_text_job_status(self.conn, job_id=int(error_job), status="error", error="ocr_tools_unavailable")

        health = self.service.search_health(
            self.conn,
            workspace="default",
            max_attachment_pending=0,
            max_ocr_pending=10,
        )

        self.assertEqual(health["status"], "fail")
        self.assertIn("OCR_ERRORS_PRESENT", health["failure_codes"])
        self.assertIn("ATTACHMENT_PENDING_HIGH", health["warning_codes"])
        self.assertIn("OCR_ISSUES_PRESENT", health["warning_codes"])
        self.assertEqual(health["extraction_thresholds"]["max_attachment_pending"], 0)
        self.assertEqual(health["extraction_thresholds"]["max_ocr_pending"], 10)

    def test_search_health_fails_on_low_ndcg_and_hit_at_10(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C123", "name": "general"})
        upsert_user(self.conn, workspace_id, {"id": "U1", "name": "alice", "real_name": "Alice Example", "profile": {"display_name": "alice"}})
        upsert_message(
            self.conn,
            workspace_id,
            "C123",
            {"ts": "1700000000.000100", "user": "U1", "text": "irrelevant first result", "channel": "C123"},
        )

        dataset = self.root / "search_eval_bad.jsonl"
        dataset.write_text(
            '{"query":"incident review","relevant":{"missing:result":2}}\n',
            encoding="utf-8",
        )

        health = self.service.search_health(
            self.conn,
            workspace="default",
            dataset_path=str(dataset),
            mode="lexical",
            limit=10,
            min_hit_at_3=0.5,
            min_hit_at_10=0.8,
            min_ndcg_at_k=0.6,
        )

        self.assertEqual(health["status"], "fail")
        self.assertIn("BENCHMARK_HIT_AT_10_LOW", health["failure_codes"])
        self.assertIn("BENCHMARK_NDCG_AT_K_LOW", health["failure_codes"])
        self.assertIn("BENCHMARK_QUERY_DEGRADATION", health["warning_codes"])
        self.assertEqual(len(health["degraded_queries"]), 1)

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

    def test_search_readiness_is_ready_with_messages_only_and_no_backlog(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C1", "name": "general"})
        upsert_message(
            self.conn,
            workspace_id,
            "C1",
            {"ts": "20.0", "text": "OpenClaw gateway is down on cooper", "user": "U1"},
        )
        process_embedding_jobs(self.conn, workspace_id=workspace_id, limit=20)

        readiness = self.service.search_readiness(self.conn, workspace="default")

        self.assertEqual(readiness["status"], "ready")
        self.assertEqual(readiness["messages"]["count"], 1)
        self.assertEqual(readiness["messages"]["embeddings"]["count"], 1)
        self.assertEqual(readiness["messages"]["embeddings"]["provider"], "local_hash")
        self.assertEqual(readiness["messages"]["embeddings"]["model"], "local-hash-128")
        self.assertEqual(readiness["messages"]["embeddings"]["configured_model_count"], 1)
        self.assertEqual(readiness["messages"]["embeddings"]["configured_model_missing"], 0)
        self.assertEqual(readiness["messages"]["embeddings"]["configured_model_coverage_ratio"], 1.0)
        self.assertTrue(readiness["messages"]["embeddings"]["configured_model_ready"])
        self.assertEqual(readiness["messages"]["embeddings"]["by_model"]["local-hash-128"], 1)
        self.assertTrue(readiness["messages"]["embeddings"]["probe"]["available"])
        self.assertEqual(readiness["derived_text"]["attachment_text"]["count"], 0)
        self.assertEqual(readiness["derived_text"]["attachment_text"]["pending"], 0)
        self.assertEqual(readiness["derived_text"]["ocr_text"]["count"], 0)
        self.assertEqual(readiness["derived_text"]["ocr_text"]["pending"], 0)

    def test_reranker_probe_reports_default_heuristic_smoke(self):
        payload = self.service.reranker_probe(
            smoke_query="gateway outage",
            smoke_documents=["gateway outage recovery", "ordinary invoice"],
        )

        self.assertTrue(payload["available"])
        self.assertEqual(payload["provider_type"], "heuristic")
        self.assertEqual(payload["model"], "BAAI/bge-reranker-v2-m3")
        self.assertTrue(payload["runtime"]["smoke"]["ok"])
        self.assertEqual(payload["runtime"]["smoke"]["documents"], 2)

    def test_search_readiness_reports_configured_model_coverage(self):
        self.config_path.write_text(
            "\n".join(
                [
                    "version: 1",
                    "storage:",
                    f"  db_path: {self.db_path}",
                    "search:",
                    "  semantic:",
                    "    model: BAAI/bge-m3",
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
        service = SlackMirrorAppService(str(self.config_path))
        conn = service.connect()
        workspace_id = service.workspace_id(conn, "default")
        upsert_channel(conn, workspace_id, {"id": "C1", "name": "general"})
        upsert_message(conn, workspace_id, "C1", {"ts": "20.0", "text": "OpenClaw gateway is down on cooper", "user": "U1"})
        process_embedding_jobs(conn, workspace_id=workspace_id, model_id="local-hash-128", limit=20)

        readiness = service.search_readiness(conn, workspace="default")

        self.assertEqual(readiness["messages"]["embeddings"]["count"], 1)
        self.assertEqual(readiness["messages"]["embeddings"]["configured_model_count"], 0)
        self.assertEqual(readiness["messages"]["embeddings"]["configured_model_missing"], 1)
        self.assertEqual(readiness["messages"]["embeddings"]["configured_model_coverage_ratio"], 0.0)
        self.assertFalse(readiness["messages"]["embeddings"]["configured_model_ready"])
        self.assertEqual(readiness["messages"]["embeddings"]["by_model"]["local-hash-128"], 1)

    def test_search_health_uses_message_embedding_provider_for_benchmark(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C123", "name": "general"})
        upsert_message(
            self.conn,
            workspace_id,
            "C123",
            {"ts": "1712870400.000100", "user": "U1", "text": "OpenClaw gateway is down on cooper", "channel": "C123"},
        )
        dataset = self.root / "search_eval_provider.jsonl"
        dataset.write_text(
            '{"query":"gateway outage on cooper","relevant":{"general:1712870400.000100":3}}\n',
            encoding="utf-8",
        )

        class FakeProvider:
            name = "fake_provider"

            def embed_texts(self, texts, *, model_id):
                vectors = []
                for text in texts:
                    normalized = str(text or "").lower()
                    if "gateway outage on cooper" in normalized or "openclaw gateway is down on cooper" in normalized:
                        vectors.append([1.0, 0.0])
                    else:
                        vectors.append([0.0, 1.0])
                return vectors

        process_embedding_jobs(self.conn, workspace_id=workspace_id, model_id="BAAI/bge-m3", limit=20, provider=FakeProvider())

        with patch.object(self.service, "message_embedding_provider", return_value=FakeProvider()):
            health = self.service.search_health(
                self.conn,
                workspace="default",
                dataset_path=str(dataset),
                mode="semantic",
                limit=5,
                model_id="BAAI/bge-m3",
            )

        self.assertIsNotNone(health["benchmark"])
        self.assertEqual(health["benchmark"]["mode"], "semantic")
        self.assertGreaterEqual(health["benchmark"]["hit_at_3"], 1.0)

    def test_search_health_warns_on_incomplete_configured_model_coverage(self):
        self.config_path.write_text(
            "\n".join(
                [
                    "version: 1",
                    "storage:",
                    f"  db_path: {self.db_path}",
                    "search:",
                    "  semantic:",
                    "    model: BAAI/bge-m3",
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
        service = SlackMirrorAppService(str(self.config_path))
        conn = service.connect()
        workspace_id = service.workspace_id(conn, "default")
        upsert_channel(conn, workspace_id, {"id": "C1", "name": "general"})
        upsert_message(conn, workspace_id, "C1", {"ts": "21.0", "text": "OpenClaw gateway is down on cooper", "user": "U1"})
        process_embedding_jobs(conn, workspace_id=workspace_id, model_id="local-hash-128", limit=20)

        health = service.search_health(conn, workspace="default")

        self.assertEqual(health["status"], "pass_with_warnings")
        self.assertIn("MESSAGE_MODEL_COVERAGE_INCOMPLETE", health["warning_codes"])

    def test_corpus_search_exact_message_query_ranks_expected_result_in_lexical_and_hybrid(self):
        workspace_id = self.service.workspace_id(self.conn, "default")
        upsert_channel(self.conn, workspace_id, {"id": "C1", "name": "alerts"})
        upsert_user(
            self.conn,
            workspace_id,
            {"id": "U1", "name": "alice", "real_name": "Alice Example", "profile": {"display_name": "alice"}},
        )
        upsert_message(
            self.conn,
            workspace_id,
            "C1",
            {"ts": "30.0", "text": "OpenClaw gateway is down on cooper", "user": "U1"},
        )
        upsert_message(
            self.conn,
            workspace_id,
            "C1",
            {"ts": "31.0", "text": "normal deployment completed successfully", "user": "U1"},
        )
        process_embedding_jobs(self.conn, workspace_id=workspace_id, limit=20)

        lexical = self.service.corpus_search(
            self.conn,
            workspace="default",
            all_workspaces=False,
            query="OpenClaw gateway is down on cooper",
            limit=5,
            mode="lexical",
        )
        hybrid = self.service.corpus_search(
            self.conn,
            workspace="default",
            all_workspaces=False,
            query="OpenClaw gateway is down on cooper",
            limit=5,
            mode="hybrid",
            model_id="local-hash-128",
        )

        self.assertGreaterEqual(len(lexical), 1)
        self.assertGreaterEqual(len(hybrid), 1)
        self.assertEqual(lexical[0]["result_kind"], "message")
        self.assertEqual(hybrid[0]["result_kind"], "message")
        self.assertIn("OpenClaw gateway is down on cooper", lexical[0]["text"])
        self.assertIn("OpenClaw gateway is down on cooper", hybrid[0]["text"])
        self.assertEqual(lexical[0]["workspace"], "default")
        self.assertEqual(hybrid[0]["workspace"], "default")
        self.assertIn("_hybrid_score", hybrid[0])

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
