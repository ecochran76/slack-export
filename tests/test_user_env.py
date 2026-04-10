import subprocess
import tempfile
import unittest
from pathlib import Path
import sqlite3

from slack_mirror.service import user_env


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
        (self.repo_root / "config.example.yaml").write_text(
            "version: 1\n"
            "storage:\n"
            "  db_path: ${SLACK_MIRROR_DB:-~/.local/state/slack-mirror/slack_mirror.db}\n"
            "workspaces:\n"
            "  - name: default\n"
            "    token: xoxb-read\n"
            "    outbound_token: xoxb-write\n",
            encoding="utf-8",
        )
        (self.repo_root / "README.md").write_text("repo snapshot\n", encoding="utf-8")
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
                stdout = "active\n" if unit == "slack-mirror-api.service" else "inactive\n"
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="services ok", stderr="")

        return calls, fake_runner

    def test_install_bootstraps_user_env(self):
        calls, runner = self._runner()

        rc = user_env.install_user_env(paths=self.paths, runner=runner, python_executable="python3", out=lambda _: None)

        self.assertEqual(rc, 0)
        self.assertTrue(self.paths.app_dir.exists())
        self.assertTrue((self.paths.app_dir / "config.example.yaml").exists())
        self.assertFalse((self.paths.app_dir / ".git").exists())
        self.assertFalse((self.paths.app_dir / "cache").exists())
        self.assertTrue(self.paths.env_path.exists())
        self.assertIn("SLACK_MIRROR_DB", self.paths.env_path.read_text(encoding="utf-8"))
        self.assertTrue(self.paths.wrapper_path.exists())
        self.assertTrue(self.paths.api_wrapper_path.exists())
        self.assertTrue(self.paths.mcp_wrapper_path.exists())
        self.assertTrue(self.paths.api_service_path.exists())
        self.assertIn('"api" "serve"', self.paths.api_wrapper_path.read_text(encoding="utf-8"))
        self.assertIn('"mcp" "serve"', self.paths.mcp_wrapper_path.read_text(encoding="utf-8"))
        self.assertIn("ExecStart=", self.paths.api_service_path.read_text(encoding="utf-8"))
        self.assertTrue(self.paths.config_path.exists())
        self.assertTrue((self.paths.config_dir / "config.example.latest.yaml").exists())
        self.assertTrue(any(call["args"][-2:] == ["mirror", "init"] for call in calls))
        self.assertTrue(any(call["args"][-2:] == ["workspaces", "sync-config"] for call in calls))
        self.assertTrue(any(call["args"][:4] == ["systemctl", "--user", "enable", "--now"] for call in calls))

    def test_install_preserves_existing_config(self):
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text("keep: true\n", encoding="utf-8")
        _, runner = self._runner()

        user_env.install_user_env(paths=self.paths, runner=runner, python_executable="python3", out=lambda _: None)

        self.assertEqual(self.paths.config_path.read_text(encoding="utf-8"), "keep: true\n")

    def test_update_runs_without_recreating_state(self):
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

        rc = user_env.update_user_env(paths=self.paths, runner=runner, python_executable="python3", out=lambda _: None)

        self.assertEqual(rc, 0)
        self.assertTrue(db_path.exists())
        conn = sqlite3.connect(db_path)
        rows = list(conn.execute("SELECT name FROM workspaces"))
        conn.close()
        self.assertEqual(rows[0][0], "default")
        self.assertEqual((self.paths.cache_dir / "cache.bin").read_text(encoding="utf-8"), "cache\n")
        self.assertIn("outbound_token: xoxb-write", self.paths.config_path.read_text(encoding="utf-8"))

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
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text("cfg\n", encoding="utf-8")
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.state_dir / "slack_mirror.db").write_text("db\n", encoding="utf-8")
        self.paths.cache_dir.mkdir(parents=True, exist_ok=True)
        output = []

        def runner(args, check=False, text=False, env=None, capture_output=False):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="svc-a\nsvc-b\n", stderr="")

        rc = user_env.status_user_env(paths=self.paths, runner=runner, out=output.append)

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("Wrapper:", rendered)
        self.assertIn("API:", rendered)
        self.assertIn("MCP:", rendered)
        self.assertIn("API svc:", rendered)
        self.assertIn("status: present", rendered)
        self.assertIn("svc-a", rendered)

    def test_validate_live_passes_for_supported_runtime_contract(self):
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
            INSERT INTO events(workspace_id, status) VALUES (1, 'done');
            INSERT INTO embedding_jobs(workspace_id, status) VALUES (1, 'done');
            """
        )
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

        self.assertEqual(rc, 0)
        rendered = "\n".join(output)
        self.assertIn("Summary: PASS", rendered)
        self.assertIn("workspace default synced into DB", rendered)
        self.assertNotIn("Recovery:", rendered)

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


if __name__ == "__main__":
    unittest.main()
