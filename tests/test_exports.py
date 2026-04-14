import json
import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.config import load_config
from slack_mirror.exports import (
    build_export_manifest,
    build_export_id,
    build_export_url,
    build_export_urls,
    delete_export_bundle,
    list_export_manifests,
    rename_export_bundle,
    resolve_export_base_url,
    resolve_export_base_urls,
    resolve_export_root,
    safe_export_path,
    select_export_url,
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

    def test_export_url_sets_and_selection(self):
        urls = build_export_urls(
            {
                "local": "http://slack.localhost",
                "external": "https://slack.ecochran.dyndns.org",
            },
            "channel-day-default-general-2026-04-12-abc123",
            "attachments/inc/report final.pdf",
        )
        self.assertEqual(
            select_export_url(urls, "external"),
            "https://slack.ecochran.dyndns.org/exports/channel-day-default-general-2026-04-12-abc123/attachments/inc/report%20final.pdf",
        )
        self.assertEqual(
            select_export_url(urls, "local"),
            "http://slack.localhost/exports/channel-day-default-general-2026-04-12-abc123/attachments/inc/report%20final.pdf",
        )

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
            self.assertEqual(
                resolve_export_base_urls(config),
                {
                    "local": "http://slack.localhost",
                    "external": "https://slack.ecochran.dyndns.org",
                },
            )

    def test_build_and_list_export_manifests(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bundle_dir = root / "channel-day-default-general-2026-04-12-abc123"
            (bundle_dir / "attachments" / "incident").mkdir(parents=True)
            (bundle_dir / "index.html").write_text("<html></html>", encoding="utf-8")
            (bundle_dir / "channel-day.json").write_text(
                json.dumps(
                    {
                        "workspace": "default",
                        "channel": "general",
                        "channel_id": "C123",
                        "day": "2026-04-12",
                        "tz": "America/Chicago",
                        "export_id": bundle_dir.name,
                    }
                ),
                encoding="utf-8",
            )
            (bundle_dir / "attachments" / "incident" / "report.pdf").write_bytes(b"%PDF-1.4\n")
            (bundle_dir / "attachments" / "incident" / "archive.bin").write_bytes(b"\x00\x01")

            manifest = build_export_manifest(
                bundle_dir,
                export_id=bundle_dir.name,
                base_urls={
                    "local": "http://slack.localhost",
                    "external": "https://slack.ecochran.dyndns.org",
                },
                default_audience="external",
            )
            self.assertEqual(manifest["bundle_url"], f"https://slack.ecochran.dyndns.org/exports/{bundle_dir.name}")
            self.assertEqual(manifest["attachment_count"], 2)
            file_map = {entry["relpath"]: entry for entry in manifest["files"]}
            self.assertEqual(file_map["index.html"]["role"], "bundle_file")
            self.assertEqual(
                file_map["attachments/incident/report.pdf"]["preview_url"],
                f"https://slack.ecochran.dyndns.org/exports/{bundle_dir.name}/attachments/incident/report.pdf/preview",
            )
            self.assertIsNone(file_map["attachments/incident/archive.bin"]["preview_url"])

            manifests = list_export_manifests(
                root,
                base_urls={"local": "http://slack.localhost"},
                default_audience="local",
            )
            self.assertEqual(len(manifests), 1)
            self.assertEqual(manifests[0]["export_id"], bundle_dir.name)

    def test_rename_export_bundle_rewrites_manifest_and_channel_day_urls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bundle_dir = root / "channel-day-default-general-2026-04-12-abc123"
            (bundle_dir / "attachments" / "incident").mkdir(parents=True)
            (bundle_dir / "index.html").write_text(
                "<a href='/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/report.pdf'>report</a>",
                encoding="utf-8",
            )
            (bundle_dir / "channel-day.json").write_text(
                json.dumps(
                    {
                        "export_id": bundle_dir.name,
                        "messages": [
                            {
                                "attachments": [
                                    {
                                        "download_url": "http://slack.localhost/exports/channel-day-default-general-2026-04-12-abc123/attachments/incident/report.pdf"
                                    }
                                ]
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (bundle_dir / "attachments" / "incident" / "report.pdf").write_bytes(b"%PDF-1.4\n")
            manifest = rename_export_bundle(
                root,
                export_id=bundle_dir.name,
                new_export_id="channel-day-default-general-renamed",
                base_urls={"local": "http://slack.localhost"},
                default_audience="local",
            )
            self.assertEqual(manifest["export_id"], "channel-day-default-general-renamed")
            self.assertTrue((root / "channel-day-default-general-renamed").exists())
            self.assertFalse(bundle_dir.exists())
            payload = json.loads((root / "channel-day-default-general-renamed" / "channel-day.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["export_id"], "channel-day-default-general-renamed")
            self.assertIn("/exports/channel-day-default-general-renamed/", (root / "channel-day-default-general-renamed" / "index.html").read_text(encoding="utf-8"))

    def test_delete_export_bundle_removes_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bundle_dir = root / "channel-day-default-general-2026-04-12-abc123"
            bundle_dir.mkdir(parents=True)
            self.assertTrue(delete_export_bundle(root, bundle_dir.name))
            self.assertFalse(delete_export_bundle(root, bundle_dir.name))
