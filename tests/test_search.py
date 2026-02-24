import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.db import apply_migrations, connect, upsert_channel, upsert_message, upsert_workspace
from slack_mirror.search.keyword import search_messages


class SearchTests(unittest.TestCase):
    def test_keyword_search_messages(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mirror.db"
            conn = connect(str(db))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))

            ws_id = upsert_workspace(conn, name="default")
            upsert_channel(conn, ws_id, {"id": "C1", "name": "general"})
            upsert_message(conn, ws_id, "C1", {"ts": "1.1", "text": "hello deploy world", "user": "U1"})
            upsert_message(conn, ws_id, "C1", {"ts": "1.2", "text": "something else", "user": "U2"})

            rows = search_messages(conn, workspace_id=ws_id, query="deploy", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertIn("deploy", rows[0]["text"])


if __name__ == "__main__":
    unittest.main()
