import io
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


if __name__ == "__main__":
    unittest.main()
