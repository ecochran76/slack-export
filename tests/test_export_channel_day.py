from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "export_channel_day.py"


class _BinaryDownloadHandler(BaseHTTPRequestHandler):
    payload = b""
    auth_header = ""

    def do_GET(self) -> None:  # noqa: N802
        if self.headers.get("Authorization") != self.auth_header:
            self.send_response(401)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


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
                CREATE TABLE channels (
                    workspace_id INTEGER,
                    channel_id TEXT,
                    name TEXT,
                    is_private INTEGER DEFAULT 0,
                    is_im INTEGER DEFAULT 0,
                    is_mpim INTEGER DEFAULT 0,
                    topic TEXT,
                    purpose TEXT,
                    raw_json TEXT
                );
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
            conn.execute(
                "INSERT INTO channels(workspace_id, channel_id, name, is_private, is_im, is_mpim, topic, purpose, raw_json) VALUES (1, 'C123', 'general', 0, 0, 0, NULL, NULL, NULL)"
            )
            conn.execute(
                "INSERT INTO users(workspace_id, user_id, raw_json) VALUES (?, ?, ?)",
                (
                    1,
                    "U123",
                    json.dumps({"profile": {"display_name": "Eric", "image_72": "https://cdn.example.test/avatar-u123.png"}}),
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
            self.assertTrue((bundle_dir / "manifest.json").exists())

            payload = json.loads((bundle_dir / "channel-day.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["public_base_url"], "http://slack.localhost")
            self.assertEqual(payload["public_base_urls"]["local"], "http://slack.localhost")
            self.assertEqual(payload["export_id"], bundle_dir.name)
            self.assertEqual(payload["messages"][0]["avatar_url"], "https://cdn.example.test/avatar-u123.png")
            self.assertEqual(payload["messages"][0]["avatar_initials"], "E")
            attachment = payload["messages"][0]["attachments"][0]
            self.assertTrue(attachment["export_relpath"].startswith("attachments/"))
            self.assertTrue((bundle_dir / attachment["export_relpath"]).exists())
            self.assertEqual(
                attachment["download_url"],
                f"http://slack.localhost/exports/{bundle_dir.name}/{attachment['export_relpath']}",
            )
            self.assertEqual(attachment["public_url"], attachment["download_url"])
            self.assertEqual(
                attachment["preview_url"],
                f"http://slack.localhost/exports/{bundle_dir.name}/{attachment['export_relpath']}/preview",
            )
            self.assertEqual(
                attachment["download_urls"]["local"],
                attachment["download_url"],
            )
            self.assertEqual(
                attachment["preview_urls"]["local"],
                attachment["preview_url"],
            )
            manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["export_id"], bundle_dir.name)
            self.assertEqual(manifest["attachment_count"], 1)
            self.assertEqual(manifest["bundle_url"], f"http://slack.localhost/exports/{bundle_dir.name}")
            relpaths = {entry["relpath"] for entry in manifest["files"]}
            self.assertIn("index.html", relpaths)
            self.assertIn("channel-day.json", relpaths)
            self.assertIn(attachment["export_relpath"], relpaths)
            html_output = (bundle_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("class='timeline'", html_output)
            self.assertIn("class='bubble'", html_output)
            self.assertIn("class='avatar'><img", html_output)
            self.assertIn("avatar-u123.png", html_output)
            self.assertIn("<code>tenant:default</code>", html_output)
            self.assertIn("<code>channel:C123</code>", html_output)
            self.assertIn("<code>file:F123</code>", html_output)
            self.assertIn("<code>application/pdf</code>", html_output)
            self.assertIn("<code>bundle:incident-report.pdf</code>", html_output)
            self.assertIn(">preview</a>", html_output)
            self.assertNotIn(f"— <code>{attachment['download_url']}</code>", html_output)
            self.assertIn(f"Download base: http://slack.localhost/exports/{bundle_dir.name}/", result.stdout)

    def test_managed_export_downloads_hosted_image_without_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "mirror.db"
            export_root = root / "exports"
            config_path = root / "config.yaml"

            _BinaryDownloadHandler.payload = b"\x89PNG\r\n\x1a\nfakepng"
            _BinaryDownloadHandler.auth_header = "Bearer xoxp-test-token"
            server = ThreadingHTTPServer(("127.0.0.1", 0), _BinaryDownloadHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                download_url = f"http://127.0.0.1:{server.server_port}/files-pri/T123-F456/image.png"
                config_path.write_text(
                    "\n".join(
                        [
                            "version: 1",
                            "storage:",
                            f"  db_path: {db_path}",
                            "exports:",
                            f"  root_dir: {export_root}",
                            "  local_base_url: http://slack.localhost",
                            "workspaces:",
                            "  - name: default",
                            "    token: xoxp-test-token",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                conn = sqlite3.connect(db_path)
                conn.executescript(
                    """
                    CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
                    CREATE TABLE channels (
                        workspace_id INTEGER,
                        channel_id TEXT,
                        name TEXT,
                        is_private INTEGER DEFAULT 0,
                        is_im INTEGER DEFAULT 0,
                        is_mpim INTEGER DEFAULT 0,
                        topic TEXT,
                        purpose TEXT,
                        raw_json TEXT
                    );
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
                conn.execute(
                    "INSERT INTO channels(workspace_id, channel_id, name, is_private, is_im, is_mpim, topic, purpose, raw_json) VALUES (1, 'C123', 'general', 0, 0, 0, NULL, NULL, NULL)"
                )
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
                    (1, "F456", None),
                )
                conn.execute(
                    "INSERT INTO messages(workspace_id, channel_id, ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        1,
                        "C123",
                        "1775926800.0",
                        "U123",
                        "Attached image",
                        None,
                        None,
                        None,
                        0,
                        json.dumps(
                            {
                                "files": [
                                    {
                                        "id": "F456",
                                        "name": "image.png",
                                        "mimetype": "image/png",
                                        "permalink": "https://polycy.slack.com/files/U123/F456/image.png",
                                        "url_private_download": download_url,
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
                subprocess.run(
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

                bundle_dir = next(export_root.iterdir())
                payload = json.loads((bundle_dir / "channel-day.json").read_text(encoding="utf-8"))
                attachment = payload["messages"][0]["attachments"][0]
                self.assertEqual(
                    attachment["download_url"],
                    f"http://slack.localhost/exports/{bundle_dir.name}/{attachment['export_relpath']}",
                )
                self.assertEqual(attachment["public_url"], attachment["download_url"])
                self.assertTrue((bundle_dir / attachment["export_relpath"]).exists())
                self.assertEqual((bundle_dir / attachment["export_relpath"]).read_bytes(), _BinaryDownloadHandler.payload)
                html_output = (bundle_dir / "index.html").read_text(encoding="utf-8")
                self.assertNotIn("https://polycy.slack.com/files/U123/F456/image.png", html_output)
                self.assertIn("data-lightbox-src=", html_output)
                self.assertIn(attachment["download_url"], html_output)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_managed_export_prefers_user_token_for_hosted_downloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "mirror.db"
            export_root = root / "exports"
            config_path = root / "config.yaml"

            _BinaryDownloadHandler.payload = b"\x89PNG\r\n\x1a\nuserpng"
            _BinaryDownloadHandler.auth_header = "Bearer xoxp-good-user-token"
            server = ThreadingHTTPServer(("127.0.0.1", 0), _BinaryDownloadHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                download_url = f"http://127.0.0.1:{server.server_port}/files-pri/T123-F789/image.png"
                config_path.write_text(
                    "\n".join(
                        [
                            "version: 1",
                            "storage:",
                            f"  db_path: {db_path}",
                            "exports:",
                            f"  root_dir: {export_root}",
                            "  local_base_url: http://slack.localhost",
                            "workspaces:",
                            "  - name: default",
                            "    token: xoxb-bad-bot-token",
                            "    user_token: xoxp-good-user-token",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                conn = sqlite3.connect(db_path)
                conn.executescript(
                    """
                    CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
                    CREATE TABLE channels (
                        workspace_id INTEGER,
                        channel_id TEXT,
                        name TEXT,
                        is_private INTEGER DEFAULT 0,
                        is_im INTEGER DEFAULT 0,
                        is_mpim INTEGER DEFAULT 0,
                        topic TEXT,
                        purpose TEXT,
                        raw_json TEXT
                    );
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
                conn.execute(
                    "INSERT INTO channels(workspace_id, channel_id, name, is_private, is_im, is_mpim, topic, purpose, raw_json) VALUES (1, 'C123', 'general', 0, 0, 0, NULL, NULL, NULL)"
                )
                conn.execute(
                    "INSERT INTO users(workspace_id, user_id, raw_json) VALUES (?, ?, ?)",
                    (1, "U123", json.dumps({"profile": {"display_name": "Eric"}})),
                )
                conn.execute(
                    "INSERT INTO files(workspace_id, file_id, local_path) VALUES (?, ?, ?)",
                    (1, "F789", None),
                )
                conn.execute(
                    "INSERT INTO messages(workspace_id, channel_id, ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        1,
                        "C123",
                        "1775926800.0",
                        "U123",
                        "Hosted image",
                        None,
                        None,
                        None,
                        0,
                        json.dumps(
                            {
                                "files": [
                                    {
                                        "id": "F789",
                                        "name": "image.png",
                                        "mimetype": "image/png",
                                        "permalink": "https://polycy.slack.com/files/U123/F789/image.png",
                                        "url_private_download": download_url,
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
                subprocess.run(
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

                bundle_dir = next(export_root.iterdir())
                payload = json.loads((bundle_dir / "channel-day.json").read_text(encoding="utf-8"))
                attachment = payload["messages"][0]["attachments"][0]
                self.assertTrue((bundle_dir / attachment["export_relpath"]).exists())
                self.assertEqual((bundle_dir / attachment["export_relpath"]).read_bytes(), _BinaryDownloadHandler.payload)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_managed_export_titles_direct_message_by_participants(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "mirror.db"
            export_root = root / "exports"
            config_path = root / "config.yaml"

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
                CREATE TABLE channels (
                    workspace_id INTEGER,
                    channel_id TEXT,
                    name TEXT,
                    is_private INTEGER DEFAULT 0,
                    is_im INTEGER DEFAULT 0,
                    is_mpim INTEGER DEFAULT 0,
                    topic TEXT,
                    purpose TEXT,
                    raw_json TEXT
                );
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
            conn.execute("INSERT INTO workspaces(id, name) VALUES (1, 'soylei')")
            conn.execute(
                "INSERT INTO channels(workspace_id, channel_id, name, is_private, is_im, is_mpim, topic, purpose, raw_json) VALUES (?, ?, ?, 0, 1, 0, NULL, NULL, ?)",
                (1, "D123", "U_BAKER", json.dumps({"id": "D123", "is_im": True, "user": "U_BAKER"})),
            )
            conn.execute(
                "INSERT INTO users(workspace_id, user_id, raw_json) VALUES (?, ?, ?)",
                (1, "U_ERIC", json.dumps({"profile": {"display_name": "Eric"}})),
            )
            conn.execute(
                "INSERT INTO users(workspace_id, user_id, raw_json) VALUES (?, ?, ?)",
                (1, "U_BAKER", json.dumps({"profile": {"display_name": "Baker"}})),
            )
            conn.execute(
                "INSERT INTO messages(workspace_id, channel_id, ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, "D123", "1775926800.0", "U_ERIC", "Hi Baker", None, None, None, 0, "{}"),
            )
            conn.execute(
                "INSERT INTO messages(workspace_id, channel_id, ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, "D123", "1775926810.0", "U_BAKER", "Hi Eric", None, None, None, 0, "{}"),
            )
            conn.commit()
            conn.close()

            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT)
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--config",
                    str(config_path),
                    "--db",
                    str(db_path),
                    "--workspace",
                    "soylei",
                    "--channel",
                    "D123",
                    "--day",
                    "2026-04-11",
                    "--managed-export",
                ],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            bundle_dir = next(export_root.iterdir())
            payload = json.loads((bundle_dir / "channel-day.json").read_text(encoding="utf-8"))
            html_output = (bundle_dir / "index.html").read_text(encoding="utf-8")
            self.assertEqual(payload["header_title"], "DM between Baker and Eric")
            self.assertEqual(payload["page_title"], "soylei DM")
            self.assertIn("<h1>DM between Baker and Eric</h1>", html_output)
            self.assertIn("<title>soylei DM 2026-04-11</title>", html_output)
            self.assertIn("<code>tenant:soylei</code>", html_output)
            self.assertIn("<code>channel:D123</code>", html_output)

    def test_managed_export_groups_consecutive_messages_by_sender(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "mirror.db"
            export_root = root / "exports"
            config_path = root / "config.yaml"

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
                CREATE TABLE channels (
                    workspace_id INTEGER,
                    channel_id TEXT,
                    name TEXT,
                    is_private INTEGER DEFAULT 0,
                    is_im INTEGER DEFAULT 0,
                    is_mpim INTEGER DEFAULT 0,
                    topic TEXT,
                    purpose TEXT,
                    raw_json TEXT
                );
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
            conn.execute(
                "INSERT INTO channels(workspace_id, channel_id, name, is_private, is_im, is_mpim, topic, purpose, raw_json) VALUES (1, 'C123', 'general', 0, 0, 0, NULL, NULL, NULL)"
            )
            conn.execute(
                "INSERT INTO users(workspace_id, user_id, raw_json) VALUES (?, ?, ?)",
                (
                    1,
                    "U123",
                    json.dumps({"profile": {"display_name": "Eric", "image_72": "https://cdn.example.test/avatar-u123.png"}}),
                ),
            )
            conn.execute(
                "INSERT INTO messages(workspace_id, channel_id, ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, "C123", "1775926800.0", "U123", "First line", None, None, None, 0, "{}"),
            )
            conn.execute(
                "INSERT INTO messages(workspace_id, channel_id, ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, "C123", "1775926810.0", "U123", "Second line", None, None, None, 0, "{}"),
            )
            conn.commit()
            conn.close()

            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT)
            subprocess.run(
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
                ],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            bundle_dir = next(export_root.iterdir())
            html_output = (bundle_dir / "index.html").read_text(encoding="utf-8")
            self.assertEqual(html_output.count("class='meta'"), 1)
            self.assertIn("class='m grouped'", html_output)
            self.assertIn("class='avatar avatar-gap' aria-hidden='true'", html_output)
            self.assertIn("First line", html_output)
            self.assertIn("Second line", html_output)

    def test_managed_export_renders_thread_identifier_as_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "mirror.db"
            export_root = root / "exports"
            config_path = root / "config.yaml"

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
                CREATE TABLE channels (
                    workspace_id INTEGER,
                    channel_id TEXT,
                    name TEXT,
                    is_private INTEGER DEFAULT 0,
                    is_im INTEGER DEFAULT 0,
                    is_mpim INTEGER DEFAULT 0,
                    topic TEXT,
                    purpose TEXT,
                    raw_json TEXT
                );
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
            conn.execute(
                "INSERT INTO channels(workspace_id, channel_id, name, is_private, is_im, is_mpim, topic, purpose, raw_json) VALUES (1, 'C123', 'general', 0, 0, 0, NULL, NULL, NULL)"
            )
            conn.execute(
                "INSERT INTO users(workspace_id, user_id, raw_json) VALUES (?, ?, ?)",
                (1, "U123", json.dumps({"profile": {"display_name": "Eric"}})),
            )
            conn.execute(
                "INSERT INTO messages(workspace_id, channel_id, ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, "C123", "1775926801.0", "U123", "Reply message", None, "1775926800.0", None, 0, "{}"),
            )
            conn.commit()
            conn.close()

            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT)
            subprocess.run(
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
                ],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            bundle_dir = next(export_root.iterdir())
            html_output = (bundle_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("<code>thread:1775926800.0</code>", html_output)

    def test_managed_export_images_use_lightbox_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "mirror.db"
            export_root = root / "exports"
            config_path = root / "config.yaml"
            attachment_path = root / "diagram.png"
            attachment_path.write_bytes(b"\x89PNG\r\n\x1a\n")

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
                CREATE TABLE channels (
                    workspace_id INTEGER,
                    channel_id TEXT,
                    name TEXT,
                    is_private INTEGER DEFAULT 0,
                    is_im INTEGER DEFAULT 0,
                    is_mpim INTEGER DEFAULT 0,
                    topic TEXT,
                    purpose TEXT,
                    raw_json TEXT
                );
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
            conn.execute(
                "INSERT INTO channels(workspace_id, channel_id, name, is_private, is_im, is_mpim, topic, purpose, raw_json) VALUES (1, 'C123', 'general', 0, 0, 0, NULL, NULL, NULL)"
            )
            conn.execute(
                "INSERT INTO users(workspace_id, user_id, raw_json) VALUES (?, ?, ?)",
                (1, "U123", json.dumps({"profile": {"display_name": "Eric"}})),
            )
            conn.execute(
                "INSERT INTO files(workspace_id, file_id, local_path) VALUES (?, ?, ?)",
                (1, "F999", str(attachment_path)),
            )
            conn.execute(
                "INSERT INTO messages(workspace_id, channel_id, ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    1,
                    "C123",
                    "1775926800.0",
                    "U123",
                    "See image",
                    None,
                    None,
                    None,
                    0,
                    json.dumps(
                        {
                            "files": [
                                {
                                    "id": "F999",
                                    "name": "diagram.png",
                                    "mimetype": "image/png",
                                    "permalink": "https://slack.example.test/files/F999",
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
            subprocess.run(
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
                ],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            bundle_dir = next(export_root.iterdir())
            html_output = (bundle_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("class='thumb-button'", html_output)
            self.assertIn("data-lightbox-src='http://slack.localhost/exports/", html_output)
            self.assertIn("class='lightbox' id='image-lightbox'", html_output)
            self.assertIn("id='image-lightbox-img'", html_output)
            self.assertIn("document.body.style.overflow='hidden'", html_output)
            self.assertNotIn("target='_blank' rel='noopener'><img class='thumb'", html_output)

    def test_managed_export_materializes_email_preview_without_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "mirror.db"
            export_root = root / "exports"
            config_path = root / "config.yaml"

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
                CREATE TABLE channels (
                    workspace_id INTEGER,
                    channel_id TEXT,
                    name TEXT,
                    is_private INTEGER DEFAULT 0,
                    is_im INTEGER DEFAULT 0,
                    is_mpim INTEGER DEFAULT 0,
                    topic TEXT,
                    purpose TEXT,
                    raw_json TEXT
                );
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
                    name TEXT,
                    title TEXT,
                    mimetype TEXT,
                    size INTEGER,
                    local_path TEXT,
                    checksum TEXT,
                    raw_json TEXT
                );
                """
            )
            conn.execute("INSERT INTO workspaces(id, name) VALUES (1, 'default')")
            conn.execute(
                "INSERT INTO channels(workspace_id, channel_id, name, is_private, is_im, is_mpim, topic, purpose, raw_json) VALUES (1, 'C123', 'general', 0, 0, 0, NULL, NULL, NULL)"
            )
            conn.execute(
                "INSERT INTO users(workspace_id, user_id, raw_json) VALUES (?, ?, ?)",
                (1, "U123", json.dumps({"profile": {"display_name": "Eric"}})),
            )
            conn.execute(
                "INSERT INTO messages(workspace_id, channel_id, ts, user_id, text, subtype, thread_ts, edited_ts, deleted, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    1,
                    "C123",
                    "1775926800.0",
                    "U123",
                    "Email attachment",
                    None,
                    None,
                    None,
                    0,
                    json.dumps(
                        {
                            "files": [
                                {
                                    "id": "FMAIL1",
                                    "name": "Re: Golf Tee Request",
                                    "title": "Re: Golf Tee Request",
                                    "mimetype": "text/html",
                                    "filetype": "email",
                                    "mode": "email",
                                    "preview": "<div>Email preview body</div>",
                                    "permalink": "https://slack.example.test/files/FMAIL1",
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
            subprocess.run(
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
                ],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            bundle_dir = next(export_root.iterdir())
            payload = json.loads((bundle_dir / "channel-day.json").read_text(encoding="utf-8"))
            attachment = payload["messages"][0]["attachments"][0]
            self.assertTrue(attachment["export_relpath"].endswith(".html"))
            self.assertEqual(attachment["mimetype"], "text/html")
            materialized = bundle_dir / attachment["export_relpath"]
            self.assertTrue(materialized.exists())
            self.assertIn("Email preview body", materialized.read_text(encoding="utf-8"))
            self.assertEqual(
                attachment["download_url"],
                f"http://slack.localhost/exports/{bundle_dir.name}/{attachment['export_relpath']}",
            )


if __name__ == "__main__":
    unittest.main()
