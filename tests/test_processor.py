import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.db import apply_migrations, connect, insert_event, upsert_workspace
from slack_mirror.service.processor import process_pending_events, run_processor_loop


class ProcessorTests(unittest.TestCase):
    def test_process_pending_message_event(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))
            ws_id = upsert_workspace(conn, name="default")

            payload = {
                "event_id": "E1",
                "event_time": 123,
                "event": {"type": "message", "channel": "C1", "ts": "1.1", "text": "hello", "user": "U1"},
            }
            insert_event(conn, ws_id, "E1", "123", "message", payload)

            result = process_pending_events(conn, ws_id, limit=10)
            self.assertEqual(result["processed"], 1)
            msg_count = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]
            self.assertEqual(msg_count, 1)

    def test_process_message_changed_and_deleted(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))
            ws_id = upsert_workspace(conn, name="default")

            changed_payload = {
                "event_id": "E2",
                "event_time": 124,
                "event": {
                    "type": "message",
                    "subtype": "message_changed",
                    "channel": "C1",
                    "message": {"ts": "2.2", "text": "edited", "user": "U1"},
                },
            }
            deleted_payload = {
                "event_id": "E3",
                "event_time": 125,
                "event": {
                    "type": "message",
                    "subtype": "message_deleted",
                    "channel": "C1",
                    "deleted_ts": "2.2",
                },
            }
            insert_event(conn, ws_id, "E2", "124", "message", changed_payload)
            insert_event(conn, ws_id, "E3", "125", "message", deleted_payload)

            result = process_pending_events(conn, ws_id, limit=10)
            self.assertEqual(result["processed"], 2)

            deleted_flag = conn.execute(
                "SELECT deleted FROM messages WHERE workspace_id = ? AND channel_id = ? AND ts = ?",
                (ws_id, "C1", "2.2"),
            ).fetchone()["deleted"]
            self.assertEqual(deleted_flag, 1)

    def test_run_processor_loop(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))
            ws_id = upsert_workspace(conn, name="default")

            payload = {
                "event_id": "E4",
                "event_time": 126,
                "event": {"type": "message", "channel": "C9", "ts": "9.9", "text": "loop", "user": "U9"},
            }
            insert_event(conn, ws_id, "E4", "126", "message", payload)

            result = run_processor_loop(conn, ws_id, limit=10, interval_seconds=0.01, max_cycles=2)
            self.assertGreaterEqual(result["cycles"], 2)
            self.assertEqual(result["processed"], 1)


if __name__ == "__main__":
    unittest.main()
