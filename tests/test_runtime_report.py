import tempfile
import unittest
from importlib import util as importlib_util
from pathlib import Path
from unittest.mock import patch


RUNTIME_REPORT_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "render_runtime_report.py"


def _load_runtime_report_module():
    spec = importlib_util.spec_from_file_location("render_runtime_report", RUNTIME_REPORT_SCRIPT)
    module = importlib_util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class RuntimeReportTests(unittest.TestCase):
    def setUp(self):
        self.module = _load_runtime_report_module()
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
        report = self.module.render_runtime_report_markdown(
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
        report = self.module.render_runtime_report_html(
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

        with patch.object(self.module, "_fetch_json", side_effect=fake_fetch) as mock_fetch:
            report = self.module.build_report(
                base_url="http://slack.localhost",
                output_format="markdown",
                timeout=7.5,
            )
        self.assertIn("Slack Mirror Runtime Report", report)
        self.assertEqual(mock_fetch.call_count, 2)

    def test_main_writes_output_file(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "runtime-report.md"
            with patch.object(
                self.module,
                "build_report",
                return_value="# report\n",
            ), patch("sys.argv", ["render_runtime_report.py", "--output", str(output)]):
                rc = self.module.main()
            self.assertEqual(rc, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "# report\n")


if __name__ == "__main__":
    unittest.main()
