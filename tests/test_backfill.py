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
    from slack_mirror.sync.backfill import backfill_messages
except ModuleNotFoundError:
    backfill_messages = None


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


if __name__ == "__main__":
    unittest.main()
