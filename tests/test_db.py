import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.db import (
    apply_migrations,
    connect,
    get_sync_state,
    list_workspaces,
    set_sync_state,
    upsert_channel,
    upsert_message,
    upsert_workspace,
)


class DbTests(unittest.TestCase):
    def test_migrate_and_upsert_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default", team_id="T123", config={"enabled": True})
            self.assertTrue(ws_id > 0)

            rows = list_workspaces(conn)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["name"], "default")

            upsert_channel(conn, ws_id, {"id": "C123", "name": "general"})
            upsert_message(conn, ws_id, "C123", {"ts": "123.45", "text": "hello", "user": "U1"})
            count = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]
            self.assertEqual(count, 1)

            set_sync_state(conn, ws_id, "messages.oldest.C123", "123.45")
            state = get_sync_state(conn, ws_id, "messages.oldest.C123")
            self.assertEqual(state, "123.45")


if __name__ == "__main__":
    unittest.main()
