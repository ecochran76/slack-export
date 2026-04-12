from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "export_channel_day.py"


class ExportChannelDayScriptTests(unittest.TestCase):
    def test_managed_export_writes_bundle_and_download_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "mirror.db"
            export_root = root / "exports"
            config_path = root / "config.yaml"
            attachment_path = root / "incident-report.pdf"
            attachment_path.write_bytes(b"%PDF-1.4\n")

            config_path.write_text(
                "\n".join(
                    [
                        "version: 1",
                        "storage:",
                        f"  db_path: {db_path}",
                        "exports:",
                        f"  root_dir: {export_root}",
                        "  local_base_url: http://slack.localhost",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
                CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT);
                CREATE TABLE users (workspace_id INTEGER, user_id TEXT, raw_json TEXT);
                CREATE TABLE messages (
                    workspace_id INTEGER,
                    channel_id TEXT,
                    ts TEXT,
                    user_id TEXT,
                    text TEXT,
                    subtype TEXT,
                    thread_ts TEXT,
                    edited_ts TEXT,
                    deleted INTEGER,
                    raw_json TEXT
                );
                CREATE TABLE files (
                    workspace_id INTEGER,
                    file_id TEXT,
                    local_path TEXT
                );
                """
            )
            conn.execute("INSERT INTO workspaces(id, name) VALUES (1, 'default')")
            conn.execute("INSERT INTO channels(workspace_id, channel_id, name) VALUES (1, 'C123', 'general')")
            conn.execute(
                "INSERT INTO users(workspace_id, user_id, raw_json) VALUES (?, ?, ?)",
                (
                    1,
                    "U123",
                    json.dumps({"profile": {"display_name": "Eric"}}),
                ),
            )
            conn.execute(
                "INSERT INTO files(workspace_id, file_id, local_path) VALUES (?, ?, ?)",
                (1, "F123", str(attachment_path)),
            )
            conn.execute(
                "INSERT INTO messages(workspace_id, channel_id, ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    1,
                    "C123",
                    "1775926800.0",
                    "U123",
                    "Incident review",
                    None,
                    None,
                    None,
                    0,
                    json.dumps(
                        {
                            "files": [
                                {
                                    "id": "F123",
                                    "name": "incident-report.pdf",
                                    "mimetype": "application/pdf",
                                    "permalink": "https://slack.example.test/files/F123",
                                }
                            ]
                        }
                    ),
                ),
            )
            conn.commit()
            conn.close()

            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--config",
                    str(config_path),
                    "--db",
                    str(db_path),
                    "--workspace",
                    "default",
                    "--channel",
                    "general",
                    "--day",
                    "2026-04-11",
                    "--managed-export",
                    "--link-audience",
                    "local",
                ],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            bundle_dirs = list(export_root.iterdir())
            self.assertEqual(len(bundle_dirs), 1)
            bundle_dir = bundle_dirs[0]
            self.assertTrue((bundle_dir / "index.html").exists())
            self.assertTrue((bundle_dir / "channel-day.json").exists())

            payload = json.loads((bundle_dir / "channel-day.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["public_base_url"], "http://slack.localhost")
            self.assertEqual(payload["export_id"], bundle_dir.name)
            attachment = payload["messages"][0]["attachments"][0]
            self.assertTrue(attachment["export_relpath"].startswith("attachments/"))
            self.assertTrue((bundle_dir / attachment["export_relpath"]).exists())
            self.assertEqual(
                attachment["download_url"],
                f"http://slack.localhost/exports/{bundle_dir.name}/{attachment['export_relpath']}",
            )
            self.assertEqual(attachment["public_url"], attachment["download_url"])
            self.assertIn(f"Download base: http://slack.localhost/exports/{bundle_dir.name}/", result.stdout)


if __name__ == "__main__":
    unittest.main()
