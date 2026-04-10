import subprocess
import tempfile
import unittest
from pathlib import Path

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
        (self.repo_root / "config.example.yaml").write_text("version: 1\nworkspaces: []\n", encoding="utf-8")
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
        self.paths.config_path.write_text("existing: true\n", encoding="utf-8")
        _, runner = self._runner()

        rc = user_env.update_user_env(paths=self.paths, runner=runner, python_executable="python3", out=lambda _: None)

        self.assertEqual(rc, 0)
        self.assertEqual(db_path.read_text(encoding="utf-8"), "db\n")
        self.assertEqual((self.paths.cache_dir / "cache.bin").read_text(encoding="utf-8"), "cache\n")
        self.assertEqual(self.paths.config_path.read_text(encoding="utf-8"), "existing: true\n")

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


if __name__ == "__main__":
    unittest.main()
