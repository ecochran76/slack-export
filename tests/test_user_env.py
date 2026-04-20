import subprocess
import tempfile
import unittest
import os
from pathlib import Path
import sqlite3
import json
import time
from types import SimpleNamespace
from unittest.mock import patch

from slack_mirror.service import user_env
from slack_mirror.service import runtime_report_user_env
from slack_mirror.service.runtime_heartbeat import write_heartbeat, write_reconcile_state


class UserEnvTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.repo_root = self.root / "repo"
        self.home_dir = self.root / "home"
        self.state_home = self.root / "state-home"
        self.cache_home = self.root / "cache-home"
        self.repo_root.mkdir()
        self.home_dir.mkdir()
        self.state_home.mkdir()
        self.cache_home.mkdir()
        self.original_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home_dir)
        self.addCleanup(self._restore_home)
        (self.repo_root / "pyproject.toml").write_text(
            "[build-system]\nrequires=[\"setuptools>=61\"]\nbuild-backend=\"setuptools.build_meta\"\n",
            encoding="utf-8",
        )
        (self.repo_root / "config.example.yaml").write_text(
            "version: 1\n"
            "dotenv: ${SLACK_MIRROR_DOTENV:-~/credentials/API-keys.env}\n"
            "storage:\n"
            "  db_path: ${SLACK_MIRROR_DB:-/__invalid__/slack_mirror.db}\n"
            "  cache_root: ${SLACK_MIRROR_CACHE:-/__invalid__/cache}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        (self.repo_root / "README.md").write_text("repo snapshot\n", encoding="utf-8")
        (self.repo_root / "slack_mirror").mkdir()
        (self.repo_root / "slack_mirror" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
        (self.repo_root / ".git").mkdir()
        (self.repo_root / ".git" / "config").write_text("ignored\n", encoding="utf-8")
        (self.repo_root / "cache").mkdir()
        (self.repo_root / "cache" / "ignored.txt").write_text("ignored\n", encoding="utf-8")
        self.paths = user_env.default_user_env_paths(
            repo_root=self.repo_root,
            home=self.home_dir,
            xdg_state_home=self.state_home,
            xdg_cache_home=self.cache_home,
        )
        self.managed_dotenv_path = self.home_dir / "credentials" / "API-keys.env"

    def _restore_home(self):
        if self.original_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.original_home

    def _runner(self):
        calls = []

        def fake_runner(args, check=False, text=False, env=None, capture_output=False):
            calls.append({"args": list(args), "env": env, "capture_output": capture_output})
            if len(args) >= 3 and args[1:3] == ["-m", "venv"]:
                venv_dir = Path(args[3])
                bin_dir = venv_dir / "bin"
                bin_dir.mkdir(parents=True, exist_ok=True)
                for name in ("python", "pip", "slack-mirror"):
                    path = bin_dir / name
                    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                    path.chmod(0o755)
            if args[-2:] == ["mirror", "init"] and env:
                db_path = Path(env["SLACK_MIRROR_DB"])
                db_path.parent.mkdir(parents=True, exist_ok=True)
                if db_path.exists():
                    db_path.unlink()
                conn = sqlite3.connect(db_path)
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS workspaces (id INTEGER PRIMARY KEY, name TEXT);
                    CREATE TABLE IF NOT EXISTS channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
                    CREATE TABLE IF NOT EXISTS messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
                    CREATE TABLE IF NOT EXISTS events (workspace_id INTEGER, status TEXT);
                    CREATE TABLE IF NOT EXISTS embedding_jobs (workspace_id INTEGER, status TEXT);
                    """
                )
                conn.close()
            if args[-2:] == ["workspaces", "sync-config"] and env:
                db_path = Path(env["SLACK_MIRROR_DB"])
                conn = sqlite3.connect(db_path)
                conn.execute("INSERT OR REPLACE INTO workspaces(id, name) VALUES (1, 'default')")
                conn.commit()
                conn.close()
            if args[:3] == ["systemctl", "--user", "is-active"]:
                unit = args[-1]
                stdout = "active\n" if unit in {
                    "slack-mirror-api.service",
                    "slack-mirror-runtime-report.timer",
                } else "inactive\n"
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="services ok", stderr="")

        return calls, fake_runner

    def _write_auth_config(self):
        db_path = self.paths.state_dir / "slack_mirror.db"
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "\n".join(
                [
                    "version: 1",
                    "storage:",
                    f"  db_path: {db_path}",
                    "service:",
                    "  auth:",
                    "    enabled: true",
                    "    allow_registration: false",
                    "workspaces:",
                    "  - name: default",
                    "    token: xoxb-test-token",
                    "    outbound_token: xoxb-outbound-token",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def test_systemctl_state_rehydrates_user_bus_env(self):
        runtime_dir = self.root / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "bus").touch()
        seen_env = {}

        def runner(args, check=False, text=False, env=None, capture_output=False):
            seen_env.update(env or {})
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="active\n", stderr="")

        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime_dir)}, clear=True):
            state = user_env._systemctl_state(runner, "slack-mirror-api.service")

        self.assertEqual(state, "active")
        self.assertEqual(seen_env["XDG_RUNTIME_DIR"], str(runtime_dir))
        self.assertEqual(seen_env["DBUS_SESSION_BUS_ADDRESS"], f"unix:path={runtime_dir / 'bus'}")

    def test_install_bootstraps_user_env(self):
        calls, runner = self._runner()

        rc = user_env.install_user_env(
            paths=self.paths,
            runner=runner,
            python_executable="python3",
            mcp_probe=lambda _: (True, None),
            out=lambda _: None,
        )

        self.assertEqual(rc, 0)
        self.assertTrue(self.paths.app_dir.exists())
        self.assertTrue((self.paths.app_dir / "config.example.yaml").exists())
        self.assertFalse((self.paths.app_dir / ".git").exists())
        self.assertFalse((self.paths.app_dir / "cache").exists())
        self.assertTrue(self.paths.env_path.exists())
        self.assertIn("SLACK_MIRROR_DB", self.paths.env_path.read_text(encoding="utf-8"))
        self.assertTrue(self.paths.wrapper_path.exists())
        self.assertTrue(self.paths.api_wrapper_path.exists())
        self.assertTrue(self.paths.inference_wrapper_path.exists())
        self.assertTrue(self.paths.mcp_wrapper_path.exists())
        self.assertTrue(self.paths.api_service_path.exists())
        self.assertTrue(self.paths.inference_service_path.exists())
        self.assertTrue(self.paths.snapshot_service_path.exists())
        self.assertTrue(self.paths.snapshot_timer_path.exists())
        self.assertTrue(self.managed_dotenv_path.exists())
        self.assertIn('"api" "serve"', self.paths.api_wrapper_path.read_text(encoding="utf-8"))
        self.assertIn('"search" "inference-serve"', self.paths.inference_wrapper_path.read_text(encoding="utf-8"))
        mcp_wrapper = self.paths.mcp_wrapper_path.read_text(encoding="utf-8")
        self.assertIn("from slack_mirror.cli.main import main", mcp_wrapper)
        self.assertIn("raise SystemExit(main())", mcp_wrapper)
        self.assertIn("'mcp',", mcp_wrapper)
        self.assertIn("'serve',", mcp_wrapper)
        self.assertNotIn("source ", mcp_wrapper)
        self.assertIn("ExecStart=", self.paths.api_service_path.read_text(encoding="utf-8"))
        self.assertIn("Slack Mirror Local Inference Service", self.paths.inference_service_path.read_text(encoding="utf-8"))
        self.assertIn("snapshot-report", self.paths.snapshot_service_path.read_text(encoding="utf-8"))
        self.assertIn("OnUnitActiveSec=1h", self.paths.snapshot_timer_path.read_text(encoding="utf-8"))
        self.assertTrue(self.paths.config_path.exists())
        self.assertTrue((self.paths.config_dir / "config.example.latest.yaml").exists())
        self.assertTrue(any(call["args"][-2:] == ["mirror", "init"] for call in calls))
        self.assertTrue(any(call["args"][-2:] == ["workspaces", "sync-config"] for call in calls))
        self.assertTrue(any(call["args"][:4] == ["systemctl", "--user", "enable", "--now"] for call in calls))
        self.assertTrue(any(call["args"][-1] == "slack-mirror-runtime-report.timer" for call in calls if call["args"][:4] == ["systemctl", "--user", "enable", "--now"]))

    def test_ensure_config_creates_missing_managed_dotenv(self):
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.app_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.app_dir / "config.example.yaml").write_text(
            "version: 1\n"
            "dotenv: ${SLACK_MIRROR_DOTENV:-~/credentials/API-keys.env}\n"
            "storage:\n"
            "  db_path: ${SLACK_MIRROR_DB:-/__invalid__/slack_mirror.db}\n"
            "workspaces:\n"
            "  - name: default\n",
            encoding="utf-8",
        )

        user_env._ensure_config(self.paths, out=lambda _: None)

        self.assertTrue(self.paths.config_path.exists())
        self.assertTrue(self.managed_dotenv_path.exists())
        self.assertIn("Managed by slack-mirror", self.managed_dotenv_path.read_text(encoding="utf-8"))

    def test_resolve_installable_repo_root_prefers_current_checkout(self):
        stale_root = self.root / "stale-site-packages"
        stale_root.mkdir()
        (stale_root / "slack_mirror").mkdir()
        (stale_root / "slack_mirror" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")

        with patch("slack_mirror.service.user_env.Path.cwd", return_value=self.repo_root):
            resolved = user_env._resolve_installable_repo_root(stale_root)

        self.assertEqual(resolved, self.repo_root.resolve())

    def test_install_preserves_existing_config(self):
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text("keep: true\n", encoding="utf-8")
        _, runner = self._runner()

        user_env.install_user_env(
            paths=self.paths,
            runner=runner,
            python_executable="python3",
            mcp_probe=lambda _: (True, None),
            out=lambda _: None,
        )
        self.assertEqual(self.paths.config_path.read_text(encoding="utf-8"), "keep: true\n")

    def test_provision_frontend_user_uses_password_env(self):
        self._write_auth_config()
        output: list[str] = []
        with patch.dict("os.environ", {"SLACK_MIRROR_BOOTSTRAP_PASSWORD": "correct-horse-123"}, clear=False):
            rc = user_env.provision_frontend_user_user_env(
                username="ecochran76@gmail.com",
                display_name="Eric Cochran",
                password_env="SLACK_MIRROR_BOOTSTRAP_PASSWORD",
                json_output=True,
                out=output.append,
                paths=self.paths,
            )
        self.assertEqual(rc, 0)
        payload = json.loads(output[-1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["user"]["username"], "ecochran76@gmail.com")
        self.assertTrue(payload["user"]["created"])
        self.assertEqual(payload["auth"]["registration_mode"], "closed")

    def test_provision_frontend_user_reports_missing_config(self):
        output: list[str] = []
        rc = user_env.provision_frontend_user_user_env(
            username="ecochran76@gmail.com",
            password="correct-horse-123",
            json_output=True,
            out=output.append,
            paths=self.paths,
        )
        self.assertEqual(rc, 1)
        payload = json.loads(output[-1])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "CONFIG_MISSING")

    def test_update_runs_without_recreating_state(self):
        self.paths.app_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.app_dir / "README.md").write_text("old snapshot\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        db_path.write_text("db\n", encoding="utf-8")
        self.paths.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.cache_dir / "cache.bin").write_text("cache\n", encoding="utf-8")
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {db_path}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        _, runner = self._runner()

        rc = user_env.update_user_env(
            paths=self.paths,
            runner=runner,
            python_executable="python3",
            mcp_probe=lambda _: (True, None),
            out=lambda _: None,
        )

        self.assertEqual(rc, 0)
        self.assertTrue(db_path.exists())
        conn = sqlite3.connect(db_path)
        rows = list(conn.execute("SELECT name FROM workspaces"))
        conn.close()
        self.assertEqual(rows[0][0], "default")
        self.assertEqual((self.paths.cache_dir / "cache.bin").read_text(encoding="utf-8"), "cache\n")
        self.assertIn("outbound_token: xoxb-write", self.paths.config_path.read_text(encoding="utf-8"))
        self.assertTrue(self.paths.backup_app_dir.exists())
        self.assertEqual((self.paths.backup_app_dir / "README.md").read_text(encoding="utf-8"), "old snapshot\n")
        self.assertEqual((self.paths.app_dir / "README.md").read_text(encoding="utf-8"), "repo snapshot\n")

    def test_update_installs_requested_extras(self):
        self.paths.app_dir.mkdir(parents=True, exist_ok=True)
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {db_path}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        calls, runner = self._runner()

        rc = user_env.update_user_env(
            paths=self.paths,
            runner=runner,
            python_executable="python3",
            extras=["local-semantic"],
            mcp_probe=lambda _: (True, None),
            out=lambda _: None,
        )

        self.assertEqual(rc, 0)
        pip_install_calls = [call["args"] for call in calls if call["args"][:3] == [str(self.paths.venv_dir / "bin" / "pip"), "install", "--upgrade"]]
        self.assertTrue(any(arg.endswith("[local-semantic]") for call in pip_install_calls for arg in call))

    def test_update_runs_silent_baseline_then_live_smoke_output(self):
        self.paths.app_dir.mkdir(parents=True, exist_ok=True)
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        self.paths.cache_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {db_path}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        _, runner = self._runner()
        output: list[str] = []

        def fake_check_live_user_env(**kwargs):
            kwargs["out"]("Managed Runtime:")
            kwargs["out"]("Combined Summary: PASS")
            return 0

        with patch("slack_mirror.service.user_env.check_live_user_env", side_effect=fake_check_live_user_env) as mock_check_live:
            rc = user_env.update_user_env(
                paths=self.paths,
                runner=runner,
                python_executable="python3",
                mcp_probe=lambda _: (True, None),
                out=output.append,
            )

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("running managed-runtime validation", rendered)
        self.assertIn("Managed Runtime:", rendered)
        self.assertIn("Combined Summary: PASS", rendered)
        self.assertNotIn("Summary: PASS with warnings", rendered)
        mock_check_live.assert_called_once()

    def test_install_fails_when_managed_mcp_probe_fails(self):
        _, runner = self._runner()
        output: list[str] = []

        rc = user_env.install_user_env(
            paths=self.paths,
            runner=runner,
            python_executable="python3",
            mcp_probe=lambda _: (False, "probe timeout"),
            out=output.append,
        )

        self.assertEqual(rc, 1)
        rendered = "\n".join(output)
        self.assertIn("MCP_SMOKE_FAILED", rendered)
        self.assertIn("Summary: FAIL", rendered)
        self.assertTrue(self.paths.snapshot_service_path.exists())
        self.assertTrue(self.paths.snapshot_timer_path.exists())

    def test_rollback_restores_previous_snapshot_and_preserves_state(self):
        current_ts = str(time.time())
        self.paths.app_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.app_dir / "README.md").write_text("current snapshot\n", encoding="utf-8")
        (self.paths.app_dir / "config.example.yaml").write_text("version: 1\n", encoding="utf-8")
        self.paths.backup_app_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.backup_app_dir / "README.md").write_text("previous snapshot\n", encoding="utf-8")
        (self.paths.backup_app_dir / "config.example.yaml").write_text("version: 1\n", encoding="utf-8")
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_timer_path.write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            """
        )
        conn.close()
        calls, runner = self._runner()

        rc = user_env.rollback_user_env(
            paths=self.paths,
            runner=runner,
            python_executable="python3",
            mcp_probe=lambda _: (True, None),
            out=lambda _: None,
        )

        self.assertEqual(rc, 0)
        self.assertEqual((self.paths.app_dir / "README.md").read_text(encoding="utf-8"), "previous snapshot\n")
        self.assertEqual((self.paths.backup_app_dir / "README.md").read_text(encoding="utf-8"), "current snapshot\n")
        self.assertTrue(db_path.exists())
        self.assertTrue(any(call["args"][:3] == ["systemctl", "--user", "restart"] for call in calls))
        self.assertTrue(self.paths.snapshot_service_path.exists())
        self.assertTrue(self.paths.snapshot_timer_path.exists())

    def test_rollback_requires_previous_snapshot(self):
        _, runner = self._runner()
        output = []

        rc = user_env.rollback_user_env(paths=self.paths, runner=runner, python_executable="python3", out=output.append)

        self.assertEqual(rc, 1)
        self.assertIn("No rollback snapshot found", "\n".join(output))

    def test_migrate_legacy_state_only_when_target_missing(self):
        self.paths.legacy_state_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.legacy_state_dir / "slack_mirror.db").write_text("legacy-db\n", encoding="utf-8")
        legacy_cache = self.paths.legacy_state_dir / "cache"
        legacy_cache.mkdir()
        (legacy_cache / "blob.txt").write_text("legacy-cache\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        self.paths.cache_dir.mkdir(parents=True, exist_ok=True)

        user_env._migrate_legacy_state(self.paths, out=lambda _: None)
        self.assertEqual((self.paths.state_dir / "slack_mirror.db").read_text(encoding="utf-8"), "legacy-db\n")
        self.assertEqual((self.paths.cache_dir / "blob.txt").read_text(encoding="utf-8"), "legacy-cache\n")

        (self.paths.state_dir / "slack_mirror.db").write_text("current-db\n", encoding="utf-8")
        (self.paths.cache_dir / "blob.txt").write_text("current-cache\n", encoding="utf-8")
        user_env._migrate_legacy_state(self.paths, out=lambda _: None)
        self.assertEqual((self.paths.state_dir / "slack_mirror.db").read_text(encoding="utf-8"), "current-db\n")
        self.assertEqual((self.paths.cache_dir / "blob.txt").read_text(encoding="utf-8"), "current-cache\n")

    def test_uninstall_preserves_data_by_default(self):
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks.service").write_text("unit\n", encoding="utf-8")
        self.paths.wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.wrapper_path.write_text("wrapper\n", encoding="utf-8")
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_timer_path.write_text("unit\n", encoding="utf-8")
        self.paths.app_dir.mkdir(parents=True, exist_ok=True)
        self.paths.venv_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        self.paths.cache_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text("cfg\n", encoding="utf-8")
        (self.paths.state_dir / "slack_mirror.db").write_text("db\n", encoding="utf-8")
        (self.paths.cache_dir / "blob.txt").write_text("cache\n", encoding="utf-8")
        calls, runner = self._runner()

        rc = user_env.uninstall_user_env(paths=self.paths, runner=runner, out=lambda _: None)

        self.assertEqual(rc, 0)
        self.assertFalse(self.paths.wrapper_path.exists())
        self.assertFalse(self.paths.api_wrapper_path.exists())
        self.assertFalse(self.paths.mcp_wrapper_path.exists())
        self.assertFalse(self.paths.api_service_path.exists())
        self.assertFalse(self.paths.snapshot_service_path.exists())
        self.assertFalse(self.paths.snapshot_timer_path.exists())
        self.assertFalse(self.paths.app_dir.exists())
        self.assertFalse(self.paths.venv_dir.exists())
        self.assertTrue(self.paths.config_path.exists())
        self.assertTrue((self.paths.state_dir / "slack_mirror.db").exists())
        self.assertTrue((self.paths.cache_dir / "blob.txt").exists())
        self.assertFalse((unit_dir / "slack-mirror-webhooks.service").exists())
        self.assertTrue(any(call["args"][:4] == ["systemctl", "--user", "disable", "--now"] for call in calls))

    def test_uninstall_purges_data_when_requested(self):
        self.paths.wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.wrapper_path.write_text("wrapper\n", encoding="utf-8")
        self.paths.app_dir.mkdir(parents=True, exist_ok=True)
        self.paths.venv_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        self.paths.cache_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text("cfg\n", encoding="utf-8")
        (self.paths.state_dir / "slack_mirror.db").write_text("db\n", encoding="utf-8")
        _, runner = self._runner()

        rc = user_env.uninstall_user_env(paths=self.paths, purge_data=True, runner=runner, out=lambda _: None)

        self.assertEqual(rc, 0)
        self.assertFalse(self.paths.config_dir.exists())
        self.assertFalse(self.paths.state_dir.exists())
        self.assertFalse(self.paths.cache_dir.exists())

    def test_status_reports_expected_presence_flags(self):
        self.paths.wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.wrapper_path.write_text("wrapper\n", encoding="utf-8")
        self.paths.api_wrapper_path.write_text("api\n", encoding="utf-8")
        self.paths.inference_wrapper_path.write_text("inference\n", encoding="utf-8")
        self.paths.mcp_wrapper_path.write_text("mcp\n", encoding="utf-8")
        self.paths.snapshot_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.snapshot_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_timer_path.write_text("unit\n", encoding="utf-8")
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n",
            encoding="utf-8",
        )
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.state_dir / "slack_mirror.db").write_text("db\n", encoding="utf-8")
        self.paths.cache_dir.mkdir(parents=True, exist_ok=True)
        write_reconcile_state(
            str(self.paths.config_path),
            workspace="default",
            auth_mode="user",
            result={
                "scanned": 10,
                "attempted": 2,
                "downloaded": 2,
                "downloaded_binary": 2,
                "materialized_email_containers": 0,
                "materialized_email_containers_with_asset_failures": 0,
                "skipped": 8,
                "failed": 0,
                "warnings": 0,
                "warning_reasons": {},
                "warning_hints": {},
                "warning_files": [],
                "failure_reasons": {},
                "failure_hints": {},
                "failed_files": [],
            },
        )
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="svc-a\nsvc-b\n", stderr="")

        rc = user_env.status_user_env(
            paths=self.paths,
            runner=runner,
            mcp_probe=lambda _: (True, None),
            out=output.append,
        )

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("Wrapper:", rendered)
        self.assertIn("API:", rendered)
        self.assertIn("Inf:", rendered)
        self.assertIn("MCP:", rendered)
        self.assertIn("API svc:", rendered)
        self.assertIn("Inf svc:", rendered)
        self.assertIn("Rpt svc:", rendered)
        self.assertIn("Rpt tmr:", rendered)
        self.assertIn("status: present", rendered)
        self.assertIn("svc-a", rendered)
        self.assertIn("concurrent probe: pass (4 clients)", rendered)
        self.assertIn("Reconcile state:", rendered)
        self.assertIn("default: downloaded=2 warnings=0 failed=0", rendered)

    def test_status_json_reports_machine_readable_presence(self):
        self.paths.wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.wrapper_path.write_text("wrapper\n", encoding="utf-8")
        self.paths.api_wrapper_path.write_text("api\n", encoding="utf-8")
        self.paths.inference_wrapper_path.write_text("inference\n", encoding="utf-8")
        self.paths.mcp_wrapper_path.write_text("mcp\n", encoding="utf-8")
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.inference_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_timer_path.write_text("unit\n", encoding="utf-8")
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "  - name: soylei\n",
            encoding="utf-8",
        )
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.state_dir / "slack_mirror.db").write_text("db\n", encoding="utf-8")
        self.paths.cache_dir.mkdir(parents=True, exist_ok=True)
        write_reconcile_state(
            str(self.paths.config_path),
            workspace="default",
            auth_mode="user",
            result={
                "scanned": 10,
                "attempted": 2,
                "downloaded": 2,
                "downloaded_binary": 1,
                "materialized_email_containers": 1,
                "materialized_email_containers_with_asset_failures": 0,
                "skipped": 8,
                "failed": 0,
                "warnings": 0,
                "warning_reasons": {},
                "warning_hints": {},
                "warning_files": [],
                "failure_reasons": {},
                "failure_hints": {},
                "failed_files": [],
            },
        )
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            if args[:3] == ["systemctl", "--user", "is-active"]:
                unit = args[-1]
                stdout = "active\n" if unit in {
                    "slack-mirror-api.service",
                    "slack-mirror-webhooks-default.service",
                    "slack-mirror-daemon-default.service",
                } else "inactive\n"
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        rc = user_env.status_user_env(
            paths=self.paths,
            runner=runner,
            mcp_probe=lambda _: (True, None),
            out=output.append,
            json_output=True,
        )

        self.assertEqual(rc, 0)
        payload = json.loads(output[0])
        self.assertTrue(payload["wrapper_present"])
        self.assertTrue(payload["api_wrapper_present"])
        self.assertTrue(payload["inference_wrapper_present"])
        self.assertTrue(payload["mcp_wrapper_present"])
        self.assertTrue(payload["mcp_smoke_ok"])
        self.assertTrue(payload["mcp_multi_client_ok"])
        self.assertIsNone(payload["mcp_multi_client_error"])
        self.assertEqual(payload["mcp_multi_client_clients"], 4)
        self.assertTrue(payload["api_service_present"])
        self.assertTrue(payload["inference_service_present"])
        self.assertTrue(payload["snapshot_service_present"])
        self.assertTrue(payload["snapshot_timer_present"])
        self.assertFalse(payload["rollback_snapshot_present"])
        self.assertEqual(payload["services"]["slack-mirror-api.service"], "active")
        self.assertEqual(payload["services"]["slack-mirror-runtime-report.timer"], "inactive")
        self.assertEqual(payload["reconcile_workspaces"][0]["name"], "default")
        self.assertTrue(payload["reconcile_workspaces"][0]["state_present"])
        self.assertEqual(payload["reconcile_workspaces"][0]["downloaded"], 2)
        self.assertEqual(payload["reconcile_workspaces"][1]["name"], "soylei")
        self.assertFalse(payload["reconcile_workspaces"][1]["state_present"])

    def test_validate_live_passes_for_supported_runtime_contract(self):
        current_ts = str(time.time())
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n"
            "    user_token: xoxp-read\n"
            "    outbound_user_token: xoxp-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_timer_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            INSERT INTO events(workspace_id, status) VALUES (1, 'done');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.close()
        write_heartbeat(str(self.paths.config_path), workspace="default", kind="daemon")
        write_reconcile_state(
            str(self.paths.config_path),
            workspace="default",
            auth_mode="user",
            result={
                "scanned": 10,
                "attempted": 2,
                "downloaded": 2,
                "downloaded_binary": 1,
                "materialized_email_containers": 1,
                "materialized_email_containers_with_asset_failures": 0,
                "skipped": 8,
                "failed": 0,
                "warnings": 0,
                "warning_reasons": {},
                "warning_hints": {},
                "warning_files": [],
                "failure_reasons": {},
                "failure_hints": {},
                "failed_files": [],
            },
        )
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit in {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
            } else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        rc = user_env.validate_live_user_env(paths=self.paths, runner=runner, out=output.append)

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("Summary: PASS", rendered)
        self.assertIn("workspace default synced into DB", rendered)
        self.assertIn("workspace default last reconcile-files (downloaded=2, warnings=0, failed=0", rendered)
        self.assertNotIn("Recovery:", rendered)

        report = user_env._build_live_validation_report(paths=self.paths, runner=runner, require_live_units=True)
        self.assertTrue(report.ok)
        self.assertEqual(report.status, "pass")
        self.assertEqual(report.failure_codes, [])
        self.assertEqual(report.warning_codes, [])
        self.assertEqual(report.workspaces[0].name, "default")
        self.assertEqual(report.workspaces[0].event_pending, 0)
        self.assertTrue(report.workspaces[0].reconcile_state_present)
        self.assertEqual(report.workspaces[0].reconcile_downloaded, 2)

    def test_validate_live_json_reports_machine_readable_failures(self):
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_timer_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            """
        )
        conn.close()
        write_heartbeat(str(self.paths.config_path), workspace="default", kind="daemon")
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit in {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
            } else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        rc = user_env.validate_live_user_env(paths=self.paths, runner=runner, out=output.append, json_output=True)

        self.assertEqual(rc, 1)
        payload = json.loads(output[0])
        self.assertEqual(payload["status"], "fail")
        self.assertIn("OUTBOUND_TOKEN_MISSING", payload["failure_codes"])
        self.assertEqual(payload["workspaces"][0]["name"], "default")

    def test_validate_live_warns_when_last_reconcile_failed(self):
        current_ts = str(time.time())
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n"
            "    user_token: xoxp-read\n"
            "    outbound_user_token: xoxp-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_timer_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            INSERT INTO events(workspace_id, status) VALUES (1, 'done');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.close()
        write_heartbeat(str(self.paths.config_path), workspace="default", kind="daemon")
        write_reconcile_state(
            str(self.paths.config_path),
            workspace="default",
            auth_mode="user",
            result={
                "scanned": 10,
                "attempted": 2,
                "downloaded": 1,
                "downloaded_binary": 1,
                "materialized_email_containers": 0,
                "materialized_email_containers_with_asset_failures": 0,
                "skipped": 8,
                "failed": 1,
                "warnings": 0,
                "warning_reasons": {},
                "warning_hints": {},
                "warning_files": [],
                "failure_reasons": {"forbidden": 1},
                "failure_hints": {"forbidden": "reauth"},
                "failed_files": [{"file_id": "F1", "reason": "forbidden", "error": "403"}],
            },
        )
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit in {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
            } else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        rc = user_env.validate_live_user_env(paths=self.paths, runner=runner, out=output.append)

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("WARN  [RECONCILE_REPAIR_FAILURES] workspace default last reconcile-files run had 1 failures", rendered)
        self.assertIn("Summary: PASS with warnings (1)", rendered)
        payload = user_env._live_validation_report_payload(
            user_env._build_live_validation_report(paths=self.paths, runner=runner, require_live_units=True)
        )
        self.assertEqual(payload["status"], "pass_with_warnings")
        self.assertIn("RECONCILE_REPAIR_FAILURES", payload["warning_codes"])
        self.assertEqual(payload["workspaces"][0]["reconcile_failed"], 1)

    def test_validate_live_warns_on_external_self_registration(self):
        current_ts = str(time.time())
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "service:\n"
            "  auth:\n"
            "    enabled: true\n"
            "    allow_registration: true\n"
            "exports:\n"
            "  external_base_url: https://slack.example.test\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n"
            "    user_token: xoxp-read\n"
            "    outbound_user_token: xoxp-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            INSERT INTO events(workspace_id, status) VALUES (1, 'done');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.close()
        write_heartbeat(str(self.paths.config_path), workspace="default", kind="daemon")
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit in {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
            } else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        rc = user_env.validate_live_user_env(paths=self.paths, runner=runner, out=output.append)

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("AUTH_REGISTRATION_EXTERNAL", rendered)
        payload = user_env._live_validation_report_payload(
            user_env._build_live_validation_report(paths=self.paths, runner=runner, require_live_units=True)
        )
        self.assertEqual(payload["status"], "pass_with_warnings")
        self.assertIn("AUTH_REGISTRATION_EXTERNAL", payload["warning_codes"])

    def test_check_live_fails_when_managed_wrappers_are_missing(self):
        current_ts = str(time.time())
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            INSERT INTO events(workspace_id, status) VALUES (1, 'done');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.close()
        write_heartbeat(str(self.paths.config_path), workspace="default", kind="daemon")
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit in {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
            } else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        rc = user_env.check_live_user_env(paths=self.paths, runner=runner, out=output.append)

        self.assertEqual(rc, 1)
        rendered = "\n".join(output)
        self.assertIn("Managed Runtime:", rendered)
        self.assertIn("wrapper: missing", rendered)
        self.assertIn("Combined Summary: FAIL", rendered)

    def test_check_live_json_combines_status_and_validation(self):
        current_ts = str(time.time())
        self.paths.wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.wrapper_path.write_text("wrapper\n", encoding="utf-8")
        self.paths.api_wrapper_path.write_text("api\n", encoding="utf-8")
        self.paths.inference_wrapper_path.write_text("inference\n", encoding="utf-8")
        self.paths.mcp_wrapper_path.write_text("mcp\n", encoding="utf-8")
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.inference_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_timer_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            INSERT INTO events(workspace_id, status) VALUES (1, 'done');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.close()
        write_heartbeat(str(self.paths.config_path), workspace="default", kind="daemon")
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            if args[:3] == ["systemctl", "--user", "is-active"]:
                unit = args[-1]
                stdout = "active\n" if unit in {
                    "slack-mirror-api.service",
                    "slack-mirror-runtime-report.timer",
                    "slack-mirror-webhooks-default.service",
                    "slack-mirror-daemon-default.service",
                } else "inactive\n"
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        rc = user_env.check_live_user_env(
            paths=self.paths,
            runner=runner,
            mcp_probe=lambda _: (True, None),
            out=output.append,
            json_output=True,
        )

        self.assertEqual(rc, 0)
        payload = json.loads(output[0])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "pass")
        self.assertIn("status_report", payload)
        self.assertIn("validation_report", payload)
        self.assertTrue(payload["status_report"]["wrapper_present"])
        self.assertTrue(payload["status_report"]["mcp_smoke_ok"])
        self.assertTrue(payload["status_report"]["mcp_multi_client_ok"])
        self.assertEqual(payload["validation_report"]["status"], "pass")

    def test_check_live_fails_when_mcp_wrapper_probe_fails(self):
        current_ts = str(time.time())
        self.paths.wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.wrapper_path.write_text("wrapper\n", encoding="utf-8")
        self.paths.api_wrapper_path.write_text("api\n", encoding="utf-8")
        self.paths.inference_wrapper_path.write_text("inference\n", encoding="utf-8")
        self.paths.mcp_wrapper_path.write_text("mcp\n", encoding="utf-8")
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            INSERT INTO events(workspace_id, status) VALUES (1, 'done');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.close()
        write_heartbeat(str(self.paths.config_path), workspace="default", kind="daemon")
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            if args[:3] == ["systemctl", "--user", "is-active"]:
                unit = args[-1]
                stdout = "active\n" if unit in {
                    "slack-mirror-api.service",
                    "slack-mirror-webhooks-default.service",
                    "slack-mirror-daemon-default.service",
                } else "inactive\n"
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        rc = user_env.check_live_user_env(
            paths=self.paths,
            runner=runner,
            mcp_probe=lambda _: (False, "probe timeout"),
            out=output.append,
        )

        self.assertEqual(rc, 1)
        rendered = "\n".join(output)
        self.assertIn("mcp probe: fail", rendered)
        self.assertIn("MCP_SMOKE_FAILED", rendered)

    def test_check_live_fails_when_mcp_multi_client_probe_fails(self):
        current_ts = str(time.time())
        self.paths.wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.wrapper_path.write_text("wrapper\n", encoding="utf-8")
        self.paths.api_wrapper_path.write_text("api\n", encoding="utf-8")
        self.paths.inference_wrapper_path.write_text("inference\n", encoding="utf-8")
        self.paths.mcp_wrapper_path.write_text("mcp\n", encoding="utf-8")
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.inference_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_timer_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            INSERT INTO events(workspace_id, status) VALUES (1, 'done');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.close()
        write_heartbeat(str(self.paths.config_path), workspace="default", kind="daemon")
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            if args[:3] == ["systemctl", "--user", "is-active"]:
                unit = args[-1]
                stdout = "active\n" if unit in {
                    "slack-mirror-api.service",
                    "slack-mirror-runtime-report.timer",
                    "slack-mirror-webhooks-default.service",
                    "slack-mirror-daemon-default.service",
                } else "inactive\n"
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        with patch.object(
            user_env,
            "_probe_managed_mcp_wrapper_multi_client",
            return_value=(False, "client 2: timeout"),
        ):
            rc = user_env.check_live_user_env(
                paths=self.paths,
                runner=runner,
                mcp_probe=lambda _: (True, None),
                out=output.append,
            )

        self.assertEqual(rc, 1)
        rendered = "\n".join(output)
        self.assertIn("mcp concurrent probe: fail (4 clients)", rendered)
        self.assertIn("client 2: timeout", rendered)
        self.assertIn("Combined Summary: FAIL (1 failure)", rendered)

    def test_check_live_fails_when_snapshot_timer_is_missing(self):
        current_ts = str(time.time())
        self.paths.wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.wrapper_path.write_text("wrapper\n", encoding="utf-8")
        self.paths.api_wrapper_path.write_text("api\n", encoding="utf-8")
        self.paths.mcp_wrapper_path.write_text("mcp\n", encoding="utf-8")
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            INSERT INTO events(workspace_id, status) VALUES (1, 'done');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.close()
        write_heartbeat(str(self.paths.config_path), workspace="default", kind="daemon")
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            if args[:3] == ["systemctl", "--user", "is-active"]:
                unit = args[-1]
                stdout = "active\n" if unit in {
                    "slack-mirror-api.service",
                    "slack-mirror-webhooks-default.service",
                    "slack-mirror-daemon-default.service",
                } else "inactive\n"
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        rc = user_env.check_live_user_env(
            paths=self.paths,
            runner=runner,
            mcp_probe=lambda _: (True, None),
            out=output.append,
        )

        self.assertEqual(rc, 1)
        rendered = "\n".join(output)
        self.assertIn("runtime-report timer file: missing", rendered)
        self.assertIn("SNAPSHOT_TIMER_FILE_MISSING", rendered)

    def test_recover_live_plans_safe_restart_and_flags_operator_only_issues(self):
        current_ts = str(time.time())
        self.paths.wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.wrapper_path.write_text("wrapper\n", encoding="utf-8")
        self.paths.api_wrapper_path.write_text("api\n", encoding="utf-8")
        self.paths.mcp_wrapper_path.write_text("mcp\n", encoding="utf-8")
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            INSERT INTO events(workspace_id, status) VALUES (1, 'done');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.close()
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            if args[:3] == ["systemctl", "--user", "is-active"]:
                unit = args[-1]
                active_units = {
                    "slack-mirror-webhooks-default.service",
                    "slack-mirror-events-default.service",
                }
                stdout = "active\n" if unit in active_units else "inactive\n"
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        rc = user_env.recover_live_user_env(paths=self.paths, runner=runner, out=output.append)

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("[RESTART_API_UNIT]", rendered)
        self.assertIn("[RESTART_WORKSPACE_UNITS] (default)", rendered)
        self.assertIn("Operator-Only Issues:", rendered)
        self.assertIn("[DUPLICATE_TOPOLOGY] (default)", rendered)
        self.assertIn("Summary: ACTIONABLE", rendered)

    def test_recover_live_plans_managed_runtime_refresh_for_mcp_drift(self):
        current_ts = str(time.time())
        self.paths.wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.wrapper_path.write_text("wrapper\n", encoding="utf-8")
        self.paths.api_wrapper_path.write_text("api\n", encoding="utf-8")
        self.paths.mcp_wrapper_path.write_text("mcp\n", encoding="utf-8")
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_timer_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            INSERT INTO events(workspace_id, status) VALUES (1, 'done');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.close()
        write_heartbeat(str(self.paths.config_path), workspace="default", kind="daemon")
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            if args[:3] == ["systemctl", "--user", "is-active"]:
                unit = args[-1]
                stdout = "active\n" if unit in {
                    "slack-mirror-api.service",
                    "slack-mirror-webhooks-default.service",
                    "slack-mirror-daemon-default.service",
                    "slack-mirror-runtime-report.timer",
                } else "inactive\n"
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        rc = user_env.recover_live_user_env(
            paths=self.paths,
            runner=runner,
            mcp_probe=lambda _: (False, "probe timeout"),
            out=output.append,
        )

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("[REFRESH_MANAGED_RUNTIME]", rendered)
        self.assertNotIn("Operator-Only Issues:", rendered)
        self.assertIn("Summary: ACTIONABLE", rendered)

    def test_recover_live_apply_restarts_units_and_rechecks(self):
        current_ts = str(time.time())
        self.paths.wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.wrapper_path.write_text("wrapper\n", encoding="utf-8")
        self.paths.api_wrapper_path.write_text("api\n", encoding="utf-8")
        self.paths.mcp_wrapper_path.write_text("mcp\n", encoding="utf-8")
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            INSERT INTO events(workspace_id, status) VALUES (1, 'done');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.close()
        output = []
        calls = []
        state = {
            "slack-mirror-api.service": "inactive",
            "slack-mirror-webhooks-default.service": "inactive",
            "slack-mirror-daemon-default.service": "inactive",
        }

        def runner(args, check=False, text=False, env=None, capture_output=False):
            calls.append(list(args))
            if args[:3] == ["systemctl", "--user", "is-active"]:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=f"{state.get(args[-1], 'inactive')}\n", stderr="")
            if args[:3] == ["systemctl", "--user", "restart"]:
                for unit in args[3:]:
                    state[unit] = "active"
                    if unit == "slack-mirror-daemon-default.service":
                        write_heartbeat(str(self.paths.config_path), workspace="default", kind="daemon")
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        rc = user_env.recover_live_user_env(paths=self.paths, runner=runner, out=output.append, apply=True, json_output=True)

        self.assertEqual(rc, 0)
        payload = json.loads(output[0])
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["applied"])

    def test_recover_live_apply_refreshes_managed_runtime(self):
        current_ts = str(time.time())
        self.paths.wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.wrapper_path.write_text("wrapper\n", encoding="utf-8")
        self.paths.api_wrapper_path.write_text("api\n", encoding="utf-8")
        self.paths.mcp_wrapper_path.write_text("mcp\n", encoding="utf-8")
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.snapshot_timer_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            INSERT INTO events(workspace_id, status) VALUES (1, 'done');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.close()
        write_heartbeat(str(self.paths.config_path), workspace="default", kind="daemon")
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            if args[:3] == ["systemctl", "--user", "is-active"]:
                unit = args[-1]
                stdout = "active\n" if unit in {
                    "slack-mirror-api.service",
                    "slack-mirror-webhooks-default.service",
                    "slack-mirror-daemon-default.service",
                    "slack-mirror-runtime-report.timer",
                } else "inactive\n"
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        with patch("slack_mirror.service.user_env.update_user_env", return_value=0) as mock_update:
            rc = user_env.recover_live_user_env(
                paths=self.paths,
                runner=runner,
                mcp_probe=lambda _: (False, "probe timeout"),
                out=output.append,
                apply=True,
                json_output=True,
            )

        self.assertEqual(rc, 0)
        mock_update.assert_called_once()
        payload = json.loads(output[0])
        self.assertTrue(payload["applied"])
        self.assertEqual(payload["status"], "actionable")

    def test_validate_live_fails_for_duplicate_topology_and_missing_outbound_tokens(self):
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            """
        )
        conn.close()
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            active_units = {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
                "slack-mirror-events-default.service",
            }
            stdout = "active\n" if unit in active_units else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        rc = user_env.validate_live_user_env(paths=self.paths, runner=runner, out=output.append)

        self.assertEqual(rc, 1)
        rendered = "\n".join(output)
        self.assertIn("FAIL  [OUTBOUND_TOKEN_MISSING]", rendered)
        self.assertIn("FAIL  [DUPLICATE_TOPOLOGY]", rendered)
        self.assertIn("Summary: FAIL", rendered)
        self.assertIn("Recovery:", rendered)
        self.assertIn("set `outbound_token` or `write_token`", rendered)
        self.assertIn("disable --now slack-mirror-events-default.service", rendered)

    def test_validate_live_passes_with_warning_actions(self):
        current_ts = str(time.time())
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '{current_ts}');
            INSERT INTO events(workspace_id, status) VALUES (1, 'error');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.commit()
        conn.close()
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit in {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
            } else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        rc = user_env.validate_live_user_env(
            paths=self.paths,
            runner=runner,
            out=output.append,
            require_live_units=False,
        )

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("Summary: PASS with warnings", rendered)
        self.assertIn("WARN  [EVENT_ERRORS]", rendered)
        self.assertIn("Warnings:", rendered)

    def test_validate_live_fails_on_queue_errors_for_full_live_gate(self):
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO events(workspace_id, status) VALUES (1, 'error');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
        conn.commit()
        conn.close()
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit in {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
            } else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        rc = user_env.validate_live_user_env(paths=self.paths, runner=runner, out=output.append)

        self.assertEqual(rc, 1)
        rendered = "\n".join(output)
        self.assertIn("FAIL  [EVENT_ERRORS]", rendered)
        self.assertIn("Summary: FAIL", rendered)

    def test_validate_live_fails_on_large_pending_backlog_for_full_live_gate(self):
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            """
        )
        conn.executemany(
            "INSERT INTO events(workspace_id, status) VALUES (1, 'pending')",
            [() for _ in range(user_env.LIVE_EVENT_PENDING_FAIL_THRESHOLD + 1)],
        )
        conn.commit()
        conn.close()
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit in {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
            } else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        rc = user_env.validate_live_user_env(paths=self.paths, runner=runner, out=output.append)

        self.assertEqual(rc, 1)
        rendered = "\n".join(output)
        self.assertIn("FAIL  [EVENT_BACKLOG]", rendered)
        self.assertIn("Summary: FAIL", rendered)

        report = user_env._build_live_validation_report(paths=self.paths, runner=runner, require_live_units=True)
        self.assertEqual(report.status, "fail")
        self.assertIn("EVENT_BACKLOG", report.failure_codes)
        self.assertEqual(report.workspaces[0].event_pending, user_env.LIVE_EVENT_PENDING_FAIL_THRESHOLD + 1)

    def test_validate_live_warns_on_stale_mirror_for_full_live_gate_without_recent_activity(self):
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        stale_ts = 1000.0
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C2', 'empty-public', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '1000.0');
            """
        )
        conn.commit()
        conn.close()
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit in {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
            } else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        with patch("slack_mirror.service.user_env.time.time", return_value=stale_ts + (user_env.LIVE_STALE_HOURS * 3600.0) + 10.0):
            write_heartbeat(
                str(self.paths.config_path),
                workspace="default",
                kind="daemon",
                extra={"ts": stale_ts + (user_env.LIVE_STALE_HOURS * 3600.0) + 9.0},
            )
            rc = user_env.validate_live_user_env(paths=self.paths, runner=runner, out=output.append)
            report = user_env._build_live_validation_report(paths=self.paths, runner=runner, require_live_units=True)

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("WARN  [STALE_MIRROR]", rendered)
        self.assertIn("Summary: PASS with warnings", rendered)
        self.assertNotIn("STALE_MIRROR", report.failure_codes)
        self.assertIn("STALE_MIRROR", report.warning_codes)
        self.assertEqual(report.workspaces[0].stale_channels, 1)
        self.assertEqual(report.workspaces[0].daemon_heartbeat_age_seconds, 1.0)
        self.assertEqual(report.workspaces[0].active_recent_channels, 0)
        self.assertEqual(report.workspaces[0].unexpected_empty_channels, 1)
        self.assertFalse(report.workspaces[0].stale_warning_suppressed)

    def test_validate_live_suppresses_stale_mirror_when_recent_activity_and_no_unexpected_empty(self):
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        stale_ts = 1000.0
        recent_ts = stale_ts + (user_env.LIVE_STALE_HOURS * 3600.0)
        conn = sqlite3.connect(db_path)
        conn.executescript(
            f"""
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'old', 0, 0, 0);
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C2', 'recent', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '1000.0');
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C2', '{recent_ts}');
            """
        )
        conn.commit()
        conn.close()
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit in {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
            } else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        with patch("slack_mirror.service.user_env.time.time", return_value=recent_ts + 10.0):
            write_heartbeat(
                str(self.paths.config_path),
                workspace="default",
                kind="daemon",
                extra={"ts": recent_ts + 9.0},
            )
            rc = user_env.validate_live_user_env(paths=self.paths, runner=runner, out=output.append)
            report = user_env._build_live_validation_report(paths=self.paths, runner=runner, require_live_units=True)

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertNotIn("WARN  [STALE_MIRROR]", rendered)
        self.assertIn("Summary: PASS", rendered)
        self.assertIn("stale mirror evidence suppressed", rendered)
        self.assertNotIn("STALE_MIRROR", report.warning_codes)
        self.assertEqual(report.workspaces[0].active_recent_channels, 1)
        self.assertEqual(report.workspaces[0].unexpected_empty_channels, 0)
        self.assertTrue(report.workspaces[0].stale_warning_suppressed)

    def test_validate_live_fails_on_missing_daemon_heartbeat_for_full_live_gate(self):
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            """
        )
        conn.commit()
        conn.close()
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit in {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
            } else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        rc = user_env.validate_live_user_env(paths=self.paths, runner=runner, out=output.append)
        report = user_env._build_live_validation_report(paths=self.paths, runner=runner, require_live_units=True)

        self.assertEqual(rc, 1)
        rendered = "\n".join(output)
        self.assertIn("FAIL  [DAEMON_HEARTBEAT_MISSING]", rendered)
        self.assertIn("Summary: FAIL", rendered)
        self.assertIn("DAEMON_HEARTBEAT_MISSING", report.failure_codes)
        self.assertIsNone(report.workspaces[0].daemon_heartbeat_age_seconds)

    def test_validate_live_suppresses_stale_mirror_for_quiet_mirrored_workspace(self):
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        stale_ts = 1000.0
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'quiet-public', 0, 0, 0);
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'D1', 'quiet-im', 1, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '1000.0');
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'D1', '1000.0');
            """
        )
        conn.commit()
        conn.close()
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit in {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
            } else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        with patch("slack_mirror.service.user_env.time.time", return_value=stale_ts + (user_env.LIVE_STALE_HOURS * 3600.0) + 10.0):
            write_heartbeat(
                str(self.paths.config_path),
                workspace="default",
                kind="daemon",
                extra={"ts": stale_ts + (user_env.LIVE_STALE_HOURS * 3600.0) + 9.0},
            )
            rc = user_env.validate_live_user_env(paths=self.paths, runner=runner, out=output.append)
            report = user_env._build_live_validation_report(paths=self.paths, runner=runner, require_live_units=True)

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertNotIn("WARN  [STALE_MIRROR]", rendered)
        self.assertIn("stale mirror evidence suppressed", rendered)
        self.assertNotIn("STALE_MIRROR", report.warning_codes)
        self.assertEqual(report.workspaces[0].active_recent_channels, 0)
        self.assertEqual(report.workspaces[0].unexpected_empty_channels, 0)
        self.assertTrue(report.workspaces[0].stale_warning_suppressed)

    def test_validate_live_warns_on_stale_mirror_for_managed_runtime_gate(self):
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        stale_ts = 1000.0
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '1000.0');
            """
        )
        conn.commit()
        conn.close()
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit == "slack-mirror-api.service" else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        with patch("slack_mirror.service.user_env.time.time", return_value=stale_ts + (user_env.LIVE_STALE_HOURS * 3600.0) + 10.0):
            rc = user_env.validate_live_user_env(
                paths=self.paths,
                runner=runner,
                out=output.append,
                require_live_units=False,
            )

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("WARN  [STALE_MIRROR]", rendered)
        self.assertIn("Summary: PASS with warnings", rendered)

    def test_validate_live_warns_on_stale_mirror_when_unexpected_empty_channels_exist(self):
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(
            "version: 1\n"
            "storage:\n"
            f"  db_path: {self.paths.state_dir / 'slack_mirror.db'}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        self.paths.api_service_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.api_service_path.write_text("unit\n", encoding="utf-8")
        unit_dir = self.home_dir / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "slack-mirror-webhooks-default.service").write_text("unit\n", encoding="utf-8")
        (unit_dir / "slack-mirror-daemon-default.service").write_text("unit\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.paths.state_dir / "slack_mirror.db"
        stale_ts = 1000.0
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE channels (workspace_id INTEGER, channel_id TEXT, name TEXT, is_im INTEGER DEFAULT 0, is_mpim INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0);
            CREATE TABLE messages (workspace_id INTEGER, channel_id TEXT, ts TEXT);
            CREATE TABLE events (workspace_id INTEGER, status TEXT);
            CREATE TABLE embedding_jobs (workspace_id INTEGER, status TEXT);
            INSERT INTO workspaces(id, name) VALUES (1, 'default');
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C1', 'general', 0, 0, 0);
            INSERT INTO channels(workspace_id, channel_id, name, is_im, is_mpim, is_private) VALUES (1, 'C2', 'empty-public', 0, 0, 0);
            INSERT INTO messages(workspace_id, channel_id, ts) VALUES (1, 'C1', '1000.0');
            """
        )
        conn.commit()
        conn.close()
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            unit = args[-1]
            stdout = "active\n" if unit in {
                "slack-mirror-api.service",
                "slack-mirror-webhooks-default.service",
                "slack-mirror-daemon-default.service",
            } else "inactive\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        with patch("slack_mirror.service.user_env.time.time", return_value=stale_ts + (user_env.LIVE_STALE_HOURS * 3600.0) + 10.0):
            write_heartbeat(
                str(self.paths.config_path),
                workspace="default",
                kind="daemon",
                extra={"ts": stale_ts + (user_env.LIVE_STALE_HOURS * 3600.0) + 9.0},
            )
            rc = user_env.validate_live_user_env(paths=self.paths, runner=runner, out=output.append)
            report = user_env._build_live_validation_report(paths=self.paths, runner=runner, require_live_units=True)

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("WARN  [STALE_MIRROR]", rendered)
        self.assertIn("Summary: PASS with warnings", rendered)
        self.assertIn("STALE_MIRROR", report.warning_codes)
        self.assertEqual(report.workspaces[0].unexpected_empty_channels, 1)
        self.assertFalse(report.workspaces[0].stale_warning_suppressed)

    def test_snapshot_runtime_report_writes_operator_summary(self):
        output: list[str] = []
        runtime_status = SimpleNamespace(
            ok=True,
            wrappers_present=True,
            api_service_present=True,
            config_present=True,
            db_present=True,
            cache_present=True,
            rollback_snapshot_present=False,
            services={"slack-mirror-api.service": "active"},
            reconcile_workspaces=[],
        )
        live_validation = SimpleNamespace(
            ok=True,
            status="pass",
            summary="Summary: PASS",
            lines=[],
            exit_code=0,
            failure_count=0,
            warning_count=0,
            failure_codes=[],
            warning_codes=[],
            workspaces=[],
        )
        with patch(
            "slack_mirror.service.runtime_report_user_env.get_app_service",
        ) as mock_get_service, patch(
            "slack_mirror.service.runtime_report_user_env.write_runtime_report_snapshot",
            return_value={
                "name": "runtime-report",
                "status": "pass",
                "markdown_path": "/tmp/report.md",
                "html_path": "/tmp/report.html",
                "latest_markdown_path": "/tmp/runtime-report.latest.md",
                "latest_html_path": "/tmp/runtime-report.latest.html",
                "latest_json_path": "/tmp/runtime-report.latest.json",
            },
        ) as mock_snapshot:
            mock_get_service.return_value.runtime_status.return_value = runtime_status
            mock_get_service.return_value.validate_live_runtime.return_value = live_validation
            rc = runtime_report_user_env.snapshot_runtime_report_user_env(
                paths=self.paths,
                out=output.append,
            )
        self.assertEqual(rc, 0)
        mock_snapshot.assert_called_once()
        kwargs = mock_snapshot.call_args.kwargs
        self.assertEqual(kwargs["runtime_status"]["ok"], True)
        self.assertEqual(kwargs["runtime_status"]["status"]["services"]["slack-mirror-api.service"], "active")
        self.assertEqual(kwargs["live_validation"]["ok"], True)
        self.assertEqual(kwargs["live_validation"]["validation"]["status"], "pass")
        joined = "\n".join(output)
        self.assertIn("Runtime report snapshot", joined)
        self.assertIn("/tmp/report.md", joined)
        self.assertIn("/tmp/runtime-report.latest.json", joined)

    def test_snapshot_runtime_report_json_outputs_machine_readable_payload(self):
        output: list[str] = []
        runtime_status = SimpleNamespace(
            ok=True,
            wrappers_present=True,
            api_service_present=True,
            config_present=True,
            db_present=True,
            cache_present=True,
            rollback_snapshot_present=False,
            services={"slack-mirror-api.service": "active"},
            reconcile_workspaces=[],
        )
        live_validation = SimpleNamespace(
            ok=True,
            status="pass",
            summary="Summary: PASS",
            lines=[],
            exit_code=0,
            failure_count=0,
            warning_count=0,
            failure_codes=[],
            warning_codes=[],
            workspaces=[],
        )
        with patch(
            "slack_mirror.service.runtime_report_user_env.get_app_service",
        ) as mock_get_service, patch(
            "slack_mirror.service.runtime_report_user_env.write_runtime_report_snapshot",
            return_value={
                "name": "runtime-report",
                "status": "pass",
                "markdown_path": "/tmp/report.md",
                "html_path": "/tmp/report.html",
                "latest_markdown_path": "/tmp/runtime-report.latest.md",
                "latest_html_path": "/tmp/runtime-report.latest.html",
                "latest_json_path": "/tmp/runtime-report.latest.json",
            },
        ):
            mock_get_service.return_value.runtime_status.return_value = runtime_status
            mock_get_service.return_value.validate_live_runtime.return_value = live_validation
            rc = runtime_report_user_env.snapshot_runtime_report_user_env(
                paths=self.paths,
                json_output=True,
                out=output.append,
            )
        self.assertEqual(rc, 0)
        payload = json.loads(output[0])
        self.assertEqual(payload["name"], "runtime-report")
        self.assertEqual(payload["status"], "pass")


if __name__ == "__main__":
    unittest.main()
