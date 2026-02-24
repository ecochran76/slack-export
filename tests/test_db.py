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
    upsert_file,
    upsert_canvas,
    upsert_channel_member,
    remove_channel_member,
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

            upsert_channel_member(conn, ws_id, "C123", "U1")
            member_count = conn.execute("SELECT COUNT(*) AS c FROM channel_members").fetchone()["c"]
            self.assertEqual(member_count, 1)
            remove_channel_member(conn, ws_id, "C123", "U1")
            member_count = conn.execute("SELECT COUNT(*) AS c FROM channel_members").fetchone()["c"]
            self.assertEqual(member_count, 0)

            set_sync_state(conn, ws_id, "messages.oldest.C123", "123.45")
            state = get_sync_state(conn, ws_id, "messages.oldest.C123")
            self.assertEqual(state, "123.45")

            upsert_file(conn, ws_id, {"id": "F1", "name": "a.txt", "title": "A"}, local_path="cache/files/F1/a.txt")
            upsert_canvas(conn, ws_id, {"id": "CV1", "title": "Canvas 1"}, local_path="cache/canvases/CV1.html")
            file_count = conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()["c"]
            canvas_count = conn.execute("SELECT COUNT(*) AS c FROM canvases").fetchone()["c"]
            self.assertEqual(file_count, 1)
            self.assertEqual(canvas_count, 1)


if __name__ == "__main__":
    unittest.main()
