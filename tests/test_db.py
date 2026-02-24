import tempfile
import unittest
from pathlib import Path

from slack_mirror.core.db import apply_migrations, connect, list_workspaces, upsert_workspace


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


if __name__ == "__main__":
    unittest.main()
