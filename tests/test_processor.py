import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.db import apply_migrations, connect, insert_event, upsert_workspace
from slack_mirror.service.processor import process_pending_events


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


if __name__ == "__main__":
    unittest.main()
