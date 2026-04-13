import tempfile
import unittest
from datetime import datetime, timezone
from importlib import util as importlib_util
from pathlib import Path
from unittest.mock import patch

from slack_mirror.service import runtime_report


RUNTIME_REPORT_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "render_runtime_report.py"


def _load_runtime_report_script_module():
    spec = importlib_util.spec_from_file_location("render_runtime_report_script", RUNTIME_REPORT_SCRIPT)
    module = importlib_util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class RuntimeReportTests(unittest.TestCase):
    def setUp(self):
        self.script_module = _load_runtime_report_script_module()
        self.runtime_status = {
            "ok": True,
            "status": {
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
                        "iso_utc": "2026-04-13T02:00:00+00:00",
                        "age_seconds": 42.0,
                        "attempted": 2,
                        "downloaded": 2,
                        "warnings": 0,
                        "failed": 0,
                    },
                    {
                        "name": "soylei",
                        "state_present": False,
                        "auth_mode": None,
                        "iso_utc": None,
                        "age_seconds": None,
                        "attempted": 0,
                        "downloaded": 0,
                        "warnings": 0,
                        "failed": 0,
                    },
                ],
            },
        }
        self.live_validation = {
            "ok": True,
            "validation": {
                "status": "pass_with_warnings",
                "summary": "Summary: PASS with warnings (1)",
                "failure_count": 0,
                "warning_count": 1,
                "failure_codes": [],
                "warning_codes": ["STALE_MIRROR"],
                "workspaces": [
                    {
                        "name": "default",
                        "event_pending": 0,
                        "embedding_pending": 0,
                        "stale_channels": 42,
                        "reconcile_state_present": True,
                        "reconcile_downloaded": 2,
                        "reconcile_warnings": 0,
                        "reconcile_failed": 0,
                        "warning_codes": ["STALE_MIRROR"],
                        "failure_codes": [],
                    }
                ],
            },
        }

    def test_render_runtime_report_markdown_includes_reconcile_summary(self):
        report = runtime_report.render_runtime_report_markdown(
            base_url="http://slack.localhost",
            fetched_at="2026-04-13T02:10:00+00:00",
            runtime_status=self.runtime_status,
            live_validation=self.live_validation,
        )
        self.assertIn("# Slack Mirror Runtime Report", report)
        self.assertIn("`default`: downloaded=`2` warnings=`0` failed=`0`, age=42s", report)
        self.assertIn("`soylei`: no persisted reconcile state", report)
        self.assertIn("`STALE_MIRROR`", report)

    def test_render_runtime_report_html_includes_status_and_workspace_cards(self):
        report = runtime_report.render_runtime_report_html(
            base_url="http://slack.localhost",
            fetched_at="2026-04-13T02:10:00+00:00",
            runtime_status=self.runtime_status,
            live_validation=self.live_validation,
        )
        self.assertIn("Slack Mirror Runtime Report", report)
        self.assertIn("Reconcile State", report)
        self.assertIn("default", report)
        self.assertIn("pass_with_warnings", report)
        self.assertIn("STALE_MIRROR", report)

    def test_build_report_fetches_both_runtime_endpoints(self):
        payloads = [self.runtime_status, self.live_validation]

        def fake_fetch(url, *, timeout):
            self.assertEqual(timeout, 7.5)
            return payloads.pop(0)

        with patch.object(runtime_report, "_fetch_json", side_effect=fake_fetch) as mock_fetch:
            report = runtime_report.build_report(
                base_url="http://slack.localhost",
                output_format="markdown",
                timeout=7.5,
            )
        self.assertIn("Slack Mirror Runtime Report", report)
        self.assertEqual(mock_fetch.call_count, 2)

    def test_write_runtime_report_snapshot_writes_timestamped_and_latest_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config_path = root / "config.yaml"
            db_path = root / "state" / "slack_mirror.db"
            config_path.write_text(
                "\n".join(["version: 1", "storage:", f"  db_path: {db_path}", ""]),
                encoding="utf-8",
            )
            with patch.object(
                runtime_report,
                "build_report_payload",
                return_value={
                    "base_url": "http://slack.localhost",
                    "fetched_at": "2026-04-13T12:00:00+00:00",
                    "runtime_status": self.runtime_status,
                    "live_validation": self.live_validation,
                },
            ):
                result = runtime_report.write_runtime_report_snapshot(
                    config_path=str(config_path),
                    base_url="http://slack.localhost",
                    name="ops snapshot",
                    timeout=5.0,
                )
            self.assertEqual(result["name"], "ops-snapshot")
            self.assertTrue(Path(result["markdown_path"]).exists())
            self.assertTrue(Path(result["html_path"]).exists())
            self.assertTrue(Path(result["latest_markdown_path"]).exists())
            self.assertTrue(Path(result["latest_html_path"]).exists())
            self.assertTrue(Path(result["latest_json_path"]).exists())
            self.assertEqual(result["kept_snapshot_sets"], 1)
            self.assertEqual(result["pruned_snapshot_sets"], 0)
            self.assertEqual(result["pruned_paths"], [])

    def test_write_runtime_report_snapshot_prunes_old_timestamped_outputs_for_same_name(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config_path = root / "config.yaml"
            db_path = root / "state" / "slack_mirror.db"
            config_path.write_text(
                "\n".join(["version: 1", "storage:", f"  db_path: {db_path}", ""]),
                encoding="utf-8",
            )
            report_dir = db_path.parent / "runtime-reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            old_md = report_dir / "ops-20260301T000000Z.md"
            old_html = report_dir / "ops-20260301T000000Z.html"
            recent_md = report_dir / "ops-20260412T120000Z.md"
            recent_html = report_dir / "ops-20260412T120000Z.html"
            other_md = report_dir / "another-20260301T000000Z.md"
            old_md.write_text("old", encoding="utf-8")
            old_html.write_text("old", encoding="utf-8")
            recent_md.write_text("recent", encoding="utf-8")
            recent_html.write_text("recent", encoding="utf-8")
            other_md.write_text("other", encoding="utf-8")
            with patch.object(
                runtime_report,
                "build_report_payload",
                return_value={
                    "base_url": "http://slack.localhost",
                    "fetched_at": "2026-04-13T12:00:00+00:00",
                    "runtime_status": self.runtime_status,
                    "live_validation": self.live_validation,
                },
            ), patch.object(
                runtime_report,
                "RUNTIME_REPORT_RETENTION_MAX_SNAPSHOTS",
                2,
            ), patch.object(
                runtime_report,
                "RUNTIME_REPORT_RETENTION_MAX_AGE_SECONDS",
                24 * 60 * 60,
            ), patch(
                "slack_mirror.service.runtime_report.datetime"
            ) as mock_datetime:
                real_datetime = datetime
                mock_datetime.now.return_value = real_datetime(2026, 4, 13, 12, 0, 0, tzinfo=timezone.utc)
                mock_datetime.strptime.side_effect = real_datetime.strptime
                result = runtime_report.write_runtime_report_snapshot(
                    config_path=str(config_path),
                    base_url="http://slack.localhost",
                    name="ops",
                    timeout=5.0,
                )
            self.assertFalse(old_md.exists())
            self.assertFalse(old_html.exists())
            self.assertTrue(recent_md.exists())
            self.assertTrue(recent_html.exists())
            self.assertTrue(other_md.exists())
            self.assertEqual(result["pruned_snapshot_sets"], 1)
            self.assertEqual(
                sorted(Path(path).name for path in result["pruned_paths"]),
                ["ops-20260301T000000Z.html", "ops-20260301T000000Z.md"],
            )

    def test_script_main_writes_output_file(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "runtime-report.md"
            with patch.object(
                self.script_module,
                "build_report",
                return_value="# report\n",
            ), patch("sys.argv", ["render_runtime_report.py", "--output", str(output)]):
                rc = self.script_module.main()
            self.assertEqual(rc, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "# report\n")


if __name__ == "__main__":
    unittest.main()
