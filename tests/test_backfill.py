import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from slack_mirror.core.db import (
    apply_migrations,
    connect,
    get_sync_state,
    set_sync_state,
    upsert_channel,
    upsert_message,
    upsert_workspace,
)

try:
    from slack_mirror.sync.backfill import backfill_messages, reconcile_file_downloads
except ModuleNotFoundError:
    backfill_messages = None
    reconcile_file_downloads = None


class _FakeApi:
    def __init__(self, token: str):
        self.token = token
        self.replies_requested: list[str] = []

    def conversation_history(self, channel_id: str, oldest: str = "0", latest: str | None = None):
        return []

    def conversation_replies(self, channel_id: str, thread_ts: str, oldest: str = "0", latest: str | None = None):
        self.replies_requested.append(thread_ts)
        if thread_ts == "1000.0":
            return [
                {"ts": "1000.0", "thread_ts": "1000.0", "text": "root", "user": "U1"},
                {"ts": "2000.0", "thread_ts": "1000.0", "text": "new reply", "user": "U2"},
            ]
        return []


class _FakeResponse:
    def __init__(self, content: bytes, content_type: str = "application/octet-stream", status_code: int = 200):
        self.content = content
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code} error")


@unittest.skipIf(backfill_messages is None, "slack_sdk not installed")
class BackfillTests(unittest.TestCase):
    def test_incremental_backfill_pulls_recent_known_thread_roots(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default", team_id="T123", config={"enabled": True})
            upsert_channel(conn, ws_id, {"id": "C123", "name": "general"})
            # Existing threaded root already known in DB, but not returned in the current
            # conversations.history slice.
            upsert_message(conn, ws_id, "C123", {"ts": "1000.0", "thread_ts": "1000.0", "text": "root", "user": "U1"})

            fake_api = _FakeApi("xoxp-test")
            with patch("slack_mirror.sync.backfill.SlackApiClient", return_value=fake_api):
                result = backfill_messages(
                    token="xoxp-test",
                    workspace_id=ws_id,
                    conn=conn,
                    oldest="1500.0",
                    channel_ids_override=["C123"],
                )

            self.assertEqual(result["channels"], 1)
            self.assertGreaterEqual(result["messages"], 2)
            self.assertIn("1000.0", fake_api.replies_requested)

            row = conn.execute(
                "SELECT text FROM messages WHERE workspace_id = ? AND channel_id = ? AND ts = ?",
                (ws_id, "C123", "2000.0"),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "new reply")

    def test_incremental_backfill_advances_checkpoint_from_reply_only_updates(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default", team_id="T123", config={"enabled": True})
            upsert_channel(conn, ws_id, {"id": "C123", "name": "general"})
            upsert_message(conn, ws_id, "C123", {"ts": "1000.0", "thread_ts": "1000.0", "text": "root", "user": "U1"})
            set_sync_state(conn, ws_id, "messages.oldest.C123", "1500.0")

            fake_api = _FakeApi("xoxp-test")
            with patch("slack_mirror.sync.backfill.SlackApiClient", return_value=fake_api):
                result = backfill_messages(
                    token="xoxp-test",
                    workspace_id=ws_id,
                    conn=conn,
                    channel_ids_override=["C123"],
                )

            self.assertEqual(result["channels"], 1)
            self.assertGreaterEqual(result["messages"], 2)
            self.assertEqual(get_sync_state(conn, ws_id, "messages.oldest.C123"), "2000.0")

    def test_reconcile_file_downloads_repairs_missing_local_files(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            cache_root = Path(td) / "cache"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default", team_id="T123", config={"enabled": True})
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, mimetype, size, local_path, checksum, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ws_id,
                    "F123",
                    "image.png",
                    "image/png",
                    12,
                    None,
                    None,
                    '{"id":"F123","name":"image.png","mimetype":"image/png","url_private_download":"https://files.slack.test/F123/download/image.png"}',
                ),
            )
            conn.commit()

            expected_local = cache_root / "files" / "F123" / "image.png"

            with patch("slack_mirror.sync.backfill.download_with_retries", return_value=(True, "abc123")) as mock_download:
                result = reconcile_file_downloads(
                    token="xoxp-test",
                    workspace_id=ws_id,
                    conn=conn,
                    cache_root=str(cache_root),
                    limit=10,
                )

            self.assertEqual(result["attempted"], 1)
            self.assertEqual(result["downloaded"], 1)
            self.assertEqual(result["downloaded_binary"], 1)
            self.assertEqual(result["materialized_email_containers"], 0)
            self.assertEqual(result["materialized_email_containers_with_asset_failures"], 0)
            self.assertEqual(result["warnings"], 0)
            self.assertEqual(result["warning_reasons"], {})
            self.assertEqual(result["warning_files"], [])
            self.assertEqual(result["failure_reasons"], {})
            self.assertEqual(result["failed_files"], [])
            mock_download.assert_called_once_with(
                "https://files.slack.test/F123/download/image.png",
                "xoxp-test",
                expected_local,
            )
            row = conn.execute(
                "SELECT local_path, checksum FROM files WHERE workspace_id = ? AND file_id = ?",
                (ws_id, "F123"),
            ).fetchone()
            self.assertEqual(row["local_path"], str(expected_local))
            self.assertEqual(row["checksum"], "abc123")

    def test_reconcile_file_downloads_skips_existing_local_files(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            cache_root = Path(td) / "cache"
            existing = cache_root / "files" / "F123" / "image.png"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_bytes(b"png")
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default", team_id="T123", config={"enabled": True})
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, mimetype, size, local_path, checksum, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ws_id,
                    "F123",
                    "image.png",
                    "image/png",
                    12,
                    str(existing),
                    "abc123",
                    '{"id":"F123","name":"image.png","mimetype":"image/png","url_private_download":"https://files.slack.test/F123/download/image.png"}',
                ),
            )
            conn.commit()

            with patch("slack_mirror.sync.backfill.download_with_retries") as mock_download:
                result = reconcile_file_downloads(
                    token="xoxp-test",
                    workspace_id=ws_id,
                    conn=conn,
                    cache_root=str(cache_root),
                    limit=10,
                )

            self.assertEqual(result["attempted"], 0)
            self.assertEqual(result["skipped"], 1)
            mock_download.assert_not_called()

    def test_reconcile_file_downloads_collects_failure_reasons(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            cache_root = Path(td) / "cache"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default", team_id="T123", config={"enabled": True})
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, mimetype, size, local_path, checksum, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ws_id,
                    "F999",
                    "bad.png",
                    "image/png",
                    12,
                    None,
                    None,
                    '{"id":"F999","name":"bad.png","mimetype":"image/png","url_private_download":"https://files.slack.test/F999/download/bad.png"}',
                ),
            )
            conn.commit()

            with patch(
                "slack_mirror.sync.backfill.download_with_retries",
                return_value=(False, "downloaded HTML interstitial instead of file content"),
            ):
                result = reconcile_file_downloads(
                    token="xoxp-test",
                    workspace_id=ws_id,
                    conn=conn,
                    cache_root=str(cache_root),
                    limit=10,
                )

            self.assertEqual(result["failed"], 1)
            self.assertEqual(result["downloaded_binary"], 0)
            self.assertEqual(result["materialized_email_containers"], 0)
            self.assertEqual(result["materialized_email_containers_with_asset_failures"], 0)
            self.assertEqual(result["warnings"], 0)
            self.assertEqual(result["failure_reasons"], {"html_interstitial": 1})
            self.assertEqual(result["failed_files"][0]["file_id"], "F999")
            self.assertEqual(result["failed_files"][0]["reason"], "html_interstitial")

    def test_reconcile_file_downloads_classifies_email_container_failures(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            cache_root = Path(td) / "cache"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default", team_id="T123", config={"enabled": True})
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, mimetype, size, local_path, checksum, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ws_id,
                    "FEMAIL",
                    "Re: Example",
                    "text/html",
                    12,
                    None,
                    None,
                    '{"id":"FEMAIL","name":"Re: Example","mimetype":"text/html","mode":"email","original_attachment_count":2,"url_private_download":"https://files.slack.test/FEMAIL/download"}',
                ),
            )
            conn.commit()

            with patch(
                "slack_mirror.sync.backfill.download_with_retries",
                return_value=(False, "downloaded HTML interstitial instead of file content"),
            ):
                result = reconcile_file_downloads(
                    token="xoxp-test",
                    workspace_id=ws_id,
                    conn=conn,
                    cache_root=str(cache_root),
                    limit=10,
                )

            self.assertEqual(result["failed"], 1)
            self.assertEqual(result["downloaded_binary"], 0)
            self.assertEqual(result["materialized_email_containers"], 0)
            self.assertEqual(result["materialized_email_containers_with_asset_failures"], 0)
            self.assertEqual(result["warnings"], 0)
            self.assertEqual(result["failure_reasons"], {"email_container_with_attachments": 1})
            self.assertEqual(result["failed_files"][0]["reason"], "email_container_with_attachments")

    def test_reconcile_file_downloads_materializes_email_container_and_inline_assets(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            cache_root = Path(td) / "cache"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default", team_id="T123", config={"enabled": True})
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, title, mimetype, size, local_path, checksum, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ws_id,
                    "FEMAIL",
                    "Re: Example",
                    "Re: Example",
                    "text/html",
                    12,
                    None,
                    None,
                    '{"id":"FEMAIL","name":"Re: Example","title":"Re: Example","mimetype":"text/html","mode":"email","preview":"<div><img src=\\"https://files-origin.slack.com/files-email-priv/T123-FEMAIL-abc/image001.jpg\\"></div>","url_private_download":"https://files.slack.test/FEMAIL/download"}',
                ),
            )
            conn.commit()

            with (
                patch("slack_mirror.sync.backfill.download_with_retries") as mock_download,
                patch(
                    "slack_mirror.sync.backfill.requests.get",
                    return_value=_FakeResponse(b"jpegbytes", content_type="image/jpeg"),
                ) as mock_get,
            ):
                result = reconcile_file_downloads(
                    token="xoxp-test",
                    workspace_id=ws_id,
                    conn=conn,
                    cache_root=str(cache_root),
                    limit=10,
                )

            self.assertEqual(result["downloaded"], 1)
            self.assertEqual(result["downloaded_binary"], 0)
            self.assertEqual(result["materialized_email_containers"], 1)
            self.assertEqual(result["materialized_email_containers_with_asset_failures"], 0)
            self.assertEqual(result["warnings"], 0)
            self.assertEqual(result["warning_reasons"], {})
            self.assertEqual(result["warning_files"], [])
            self.assertEqual(result["failed"], 0)
            mock_download.assert_not_called()
            mock_get.assert_called_once()
            row = conn.execute(
                "SELECT local_path, checksum FROM files WHERE workspace_id = ? AND file_id = ?",
                (ws_id, "FEMAIL"),
            ).fetchone()
            self.assertIsNotNone(row)
            local_path = Path(row["local_path"])
            self.assertTrue(local_path.exists())
            self.assertEqual(local_path.suffix, ".html")
            html_text = local_path.read_text(encoding="utf-8")
            self.assertIn(f"{local_path.stem}_assets/image001.jpg", html_text)
            asset_path = local_path.parent / f"{local_path.stem}_assets" / "image001.jpg"
            self.assertTrue(asset_path.exists())

    def test_reconcile_file_downloads_warns_when_email_assets_are_partial(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            cache_root = Path(td) / "cache"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default", team_id="T123", config={"enabled": True})
            conn.execute(
                """
                INSERT INTO files(workspace_id, file_id, name, title, mimetype, size, local_path, checksum, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ws_id,
                    "FEMAIL",
                    "Re: Example",
                    "Re: Example",
                    "text/html",
                    12,
                    None,
                    None,
                    '{"id":"FEMAIL","name":"Re: Example","title":"Re: Example","mimetype":"text/html","mode":"email","preview":"<div><img src=\\"https://files-origin.slack.com/files-email-priv/T123-FEMAIL-abc/image001.jpg\\"><img src=\\"https://files-origin.slack.com/files-email-priv/T123-FEMAIL-abc/image002.jpg\\"></div>","url_private_download":"https://files.slack.test/FEMAIL/download"}',
                ),
            )
            conn.commit()

            def fake_get(url, headers=None, timeout=60):
                if url.endswith("image001.jpg"):
                    return _FakeResponse(b"jpegbytes", content_type="image/jpeg")
                raise RuntimeError("403 forbidden")

            with (
                patch("slack_mirror.sync.backfill.download_with_retries") as mock_download,
                patch("slack_mirror.sync.backfill.requests.get", side_effect=fake_get) as mock_get,
            ):
                result = reconcile_file_downloads(
                    token="xoxp-test",
                    workspace_id=ws_id,
                    conn=conn,
                    cache_root=str(cache_root),
                    limit=10,
                )

            self.assertEqual(result["downloaded"], 1)
            self.assertEqual(result["materialized_email_containers"], 1)
            self.assertEqual(result["materialized_email_containers_with_asset_failures"], 1)
            self.assertEqual(result["warnings"], 1)
            self.assertEqual(result["warning_reasons"], {"email_container_inline_assets_partial": 1})
            self.assertEqual(result["warning_files"][0]["reason"], "email_container_inline_assets_partial")
            self.assertEqual(result["warning_files"][0]["asset_total"], 2)
            self.assertEqual(result["warning_files"][0]["asset_downloaded"], 1)
            self.assertEqual(result["warning_files"][0]["asset_failed"], 1)
            self.assertEqual(result["failed"], 0)
            mock_download.assert_not_called()
            self.assertEqual(mock_get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
