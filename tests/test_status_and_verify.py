import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from slack_mirror.cli.main import cmd_mirror_status, cmd_workspaces_verify
from slack_mirror.core.db import apply_migrations, connect, upsert_channel, upsert_workspace


class StatusAndVerifyTests(unittest.TestCase):
    def test_workspaces_verify_fails_for_missing_workspace_name(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "config.yaml"
            cfg.write_text(
                "workspaces:\n"
                "  - name: default\n"
                "    token: xoxb-test\n",
                encoding="utf-8",
            )
            args = SimpleNamespace(config=str(cfg), workspace="missing")

            with self.assertRaisesRegex(ValueError, "Workspace 'missing' not found in config"):
                cmd_workspaces_verify(args)

    def test_mirror_status_fails_for_missing_workspace_in_db(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            cfg = td_path / "config.yaml"
            cfg.write_text(
                "storage:\n"
                "  db_path: ./mirror.db\n"
                "workspaces:\n"
                "  - name: default\n",
                encoding="utf-8",
            )

            conn = connect(str(td_path / "mirror.db"))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))
            ws_id = upsert_workspace(conn, name="default")
            upsert_channel(conn, ws_id, {"id": "C1", "name": "general"})

            args = SimpleNamespace(
                config=str(cfg),
                stale_hours=24.0,
                workspace="missing",
                max_zero_msg=0,
                max_stale=0,
                enforce_stale=False,
                classify_access=False,
                classify_limit=20,
                json=True,
                healthy=True,
                fail_on_gap=False,
            )

            with self.assertRaisesRegex(ValueError, "Workspace 'missing' not found in DB"):
                with redirect_stdout(io.StringIO()):
                    cmd_mirror_status(args)

    def test_workspaces_verify_can_require_explicit_outbound_tokens(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "config.yaml"
            cfg.write_text(
                "workspaces:\n"
                "  - name: default\n"
                "    token: xoxb-test\n"
                "    user_token: xoxp-test\n",
                encoding="utf-8",
            )
            args = SimpleNamespace(config=str(cfg), workspace=None, require_explicit_outbound=True)

            with patch("slack_mirror.core.slack_api.safe_auth_test", return_value=(True, "ok")):
                with redirect_stdout(io.StringIO()) as out:
                    rc = cmd_workspaces_verify(args)

            self.assertEqual(rc, 1)
            rendered = out.getvalue()
            self.assertIn("missing_outbound_token", rendered)
            self.assertIn("missing_outbound_user_token", rendered)

    def test_workspaces_verify_passes_with_explicit_outbound_tokens(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "config.yaml"
            cfg.write_text(
                "workspaces:\n"
                "  - name: default\n"
                "    token: xoxb-test\n"
                "    outbound_token: xoxb-write\n"
                "    user_token: xoxp-test\n"
                "    outbound_user_token: xoxp-write\n",
                encoding="utf-8",
            )
            args = SimpleNamespace(config=str(cfg), workspace=None, require_explicit_outbound=True)

            with patch("slack_mirror.core.slack_api.safe_auth_test", return_value=(True, "ok")):
                with redirect_stdout(io.StringIO()):
                    rc = cmd_workspaces_verify(args)

            self.assertEqual(rc, 0)

    def test_mirror_status_classify_access_respects_workspace_filter_and_reports_examples(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            cfg = td_path / "config.yaml"
            cfg.write_text(
                "storage:\n"
                "  db_path: ./mirror.db\n"
                "workspaces:\n"
                "  - name: default\n"
                "  - name: other\n",
                encoding="utf-8",
            )

            conn = connect(str(td_path / "mirror.db"))
            migrations = Path(__file__).resolve().parents[1] / "slack_mirror" / "core" / "migrations"
            apply_migrations(conn, str(migrations))
            default_id = upsert_workspace(conn, name="default")
            other_id = upsert_workspace(conn, name="other")
            upsert_channel(conn, default_id, {"id": "C_ACTIVE", "name": "active"})
            upsert_channel(conn, default_id, {"id": "C_OLD", "name": "archive"})
            upsert_channel(conn, default_id, {"id": "C_ZERO", "name": "empty"})
            upsert_channel(conn, other_id, {"id": "C_OTHER", "name": "other-room"})
            conn.execute(
                "INSERT INTO messages(workspace_id, channel_id, ts) VALUES (?, ?, ?)",
                (default_id, "C_ACTIVE", "200000.0"),
            )
            conn.execute(
                "INSERT INTO messages(workspace_id, channel_id, ts) VALUES (?, ?, ?)",
                (default_id, "C_OLD", "1000.0"),
            )
            conn.execute(
                "INSERT INTO messages(workspace_id, channel_id, ts) VALUES (?, ?, ?)",
                (other_id, "C_OTHER", "1000.0"),
            )
            conn.commit()

            args = SimpleNamespace(
                config=str(cfg),
                stale_hours=24.0,
                workspace="default",
                max_zero_msg=0,
                max_stale=0,
                enforce_stale=True,
                classify_access=True,
                classify_limit=5,
                json=True,
                healthy=True,
                fail_on_gap=False,
            )

            with patch("slack_mirror.cli.main.time.time", return_value=200000.0):
                with redirect_stdout(io.StringIO()) as out:
                    rc = cmd_mirror_status(args)

            self.assertEqual(rc, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(len(payload["access_classification"]), 1)
            row = payload["access_classification"][0]
            self.assertEqual(row["workspace"], "default")
            self.assertEqual(row["total_channels"], 3)
            self.assertEqual(row["A_mirrored_inactive"], 1)
            self.assertEqual(row["B_active_recent"], 1)
            self.assertEqual(row["C_zero_message"], 1)
            self.assertEqual(row["interpretation"], "active_recent_activity_present")
            self.assertEqual(row["C_shell_like"], 0)
            self.assertEqual(row["C_unexpected_empty"], 1)
            self.assertEqual(row["A_mirrored_inactive_examples"][0]["channel_id"], "C_OLD")
            self.assertEqual(row["A_mirrored_inactive_examples"][0]["channel_class"], "public")
            self.assertIsInstance(row["A_mirrored_inactive_examples"][0]["last_message_age_hours"], float)
            self.assertEqual(row["C_zero_message_examples"][0]["channel_id"], "C_ZERO")
            self.assertEqual(row["C_zero_message_examples"][0]["channel_class"], "public")
            self.assertEqual(row["C_zero_message_examples"][0]["status"], "unexpected_empty_channel")
            self.assertIsNone(row["C_zero_message_examples"][0]["last_message_ts"])


if __name__ == "__main__":
    unittest.main()
