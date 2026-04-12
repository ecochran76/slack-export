import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.config import load_config
from slack_mirror.exports import (
    build_export_id,
    build_export_url,
    resolve_export_base_url,
    resolve_export_root,
    safe_export_path,
)


class ExportHelpersTests(unittest.TestCase):
    def test_build_export_id_is_deterministic_and_human_readable(self):
        first = build_export_id(
            "channel-day",
            workspace="default",
            channel="general-business-4",
            day="2026-04-12",
        )
        second = build_export_id(
            "channel-day",
            workspace="default",
            channel="general-business-4",
            day="2026-04-12",
        )

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("channel-day-default-general-business-4-2026-04-12-"))
        self.assertLessEqual(len(first), 63)

    def test_export_urls_use_expected_shape(self):
        url = build_export_url(
            "https://slack.ecochran.dyndns.org",
            "channel-day-default-general-2026-04-12-abc123",
            "attachments/inc/report final.pdf",
        )
        preview = build_export_url(
            "http://slack.localhost",
            "channel-day-default-general-2026-04-12-abc123",
            "attachments/inc/report final.pdf",
            preview=True,
        )

        self.assertEqual(
            url,
            "https://slack.ecochran.dyndns.org/exports/channel-day-default-general-2026-04-12-abc123/attachments/inc/report%20final.pdf",
        )
        self.assertEqual(
            preview,
            "http://slack.localhost/exports/channel-day-default-general-2026-04-12-abc123/attachments/inc/report%20final.pdf/preview",
        )

    def test_safe_export_path_rejects_escape(self):
        root = Path("/tmp/exports-root")
        with self.assertRaises(ValueError):
            safe_export_path(root, "example-export", "../secret.txt")

    def test_export_root_and_base_url_resolve_from_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config.yaml"
            exports_root = root / "user-exports"
            config_path.write_text(
                "\n".join(
                    [
                        "version: 1",
                        "storage:",
                        f"  db_path: {root / 'mirror.db'}",
                        "exports:",
                        f"  root_dir: {exports_root}",
                        "  local_base_url: http://slack.localhost",
                        "  external_base_url: https://slack.ecochran.dyndns.org",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)
            self.assertEqual(resolve_export_root(config), exports_root.resolve())
            self.assertEqual(resolve_export_base_url(config, audience="local"), "http://slack.localhost")
            self.assertEqual(
                resolve_export_base_url(config, audience="external"),
                "https://slack.ecochran.dyndns.org",
            )
